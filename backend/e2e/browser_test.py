"""Real-browser integration test with a separate local DynamoDB emulator.

Run from the repository root using backend's Python plus requirements.txt here.
No real AWS credentials, tables, browser profiles, or live game state are used.
"""

import json
import logging
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.request

import boto3
from moto.server import ThreadedMotoServer
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from archive import query_records  # noqa: E402
from export_history import player_report  # noqa: E402

APP_PYTHON = ROOT / "backend" / "venv" / "bin" / "python"
OUT = ROOT / ".artifacts" / "e2e"
OUT.mkdir(parents=True, exist_ok=True)
checks = []
processes = []
logs = []


def check(name, condition=True):
    assert condition, name
    checks.append(name)
    print(f"PASS: {name}", flush=True)


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start(command, cwd, env, name):
    log = (OUT / f"{name}.log").open("a")
    logs.append(log)
    proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log)
    processes.append(proc)
    return proc


def healthy(url):
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def await_server(url, proc):
    for _ in range(150):
        if healthy(url):
            return
        assert proc.poll() is None, f"Process exited; inspect {OUT}"
        time.sleep(0.1)
    raise AssertionError(f"Server did not become ready: {url}")


INIT = """(() => {
 const WS = window.WebSocket;
 window.__e2e = {state:null, id:null, errors:[], socket:null};
 window.WebSocket = class extends WS {
  constructor(...args) {
   super(...args); window.__e2e.socket = this;
   this.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if(message.type === 'state') window.__e2e.state = message.state;
    if(message.type === 'session') window.__e2e.id = message.id;
    if(message.type === 'error') window.__e2e.errors.push(message.message);
   });
  }
 };
})();"""


def state(page):
    return page.evaluate("window.__e2e.state")


def wait(page, predicate):
    page.wait_for_function(f"window.__e2e && ({predicate})", timeout=20000)


def ready(page):
    wait(page, "window.__e2e.state !== null")
    expect(page.get_by_text("Connected", exact=True)).to_be_visible()


def player_stack(page):
    s = state(page)
    return next(p["stack"] for p in s["players"] if p["id"] == s["you"])


def raw(page, message):
    page.evaluate("m => window.__e2e.socket.send(JSON.stringify(m))", message)


def join(context, name, url):
    page = context.new_page()
    page.goto(url)
    page.get_by_label("Your name", exact=True).fill(name)
    page.get_by_role("button", name="Join table", exact=True).click()
    ready(page)
    return page


def set_stack(page, amount):
    current = state(page)
    name = next(p["name"] for p in current["players"] if p["id"] == current["you"])
    page.get_by_role("button", name=f"Player options for {name}", exact=True).click()
    page.get_by_label("Your stack", exact=True).fill(str(amount))
    page.get_by_role("button", name="Set stack", exact=True).click()
    wait(
        page,
        f"window.__e2e.state.players.find(p=>p.id===window.__e2e.state.you).stack === {amount}",
    )


def run(feedback_only=False):
    for filename in ("report.json", "player-export.json"):
        (OUT / filename).unlink(missing_ok=True)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    db_port, api_port, ui_port = port(), port(), port()
    emulator = ThreadedMotoServer(ip_address="127.0.0.1", port=db_port, verbose=False)
    emulator.start()
    env = os.environ.copy()
    # The app and export command use production dependencies, not test-runner packages.
    env.pop("PYTHONPATH", None)
    for key in list(env):
        if key.startswith("AWS_") or key.startswith("DYNAMODB_"):
            env.pop(key)
    env.update(
        AWS_ACCESS_KEY_ID="testing",
        AWS_SECRET_ACCESS_KEY="testing",
        AWS_REGION="us-east-1",
        AWS_DEFAULT_REGION="us-east-1",
        AWS_EC2_METADATA_DISABLED="true",
        AWS_CONFIG_FILE=os.devnull,
        AWS_SHARED_CREDENTIALS_FILE=os.devnull,
        AWS_ENDPOINT_URL_DYNAMODB=f"http://127.0.0.1:{db_port}",
        DYNAMODB_TABLE="e2e-game",
        DYNAMODB_HISTORY_TABLE="e2e-history",
        VITE_WS_URL=f"ws://127.0.0.1:{api_port}/ws",
    )
    test_config = OUT / "aws-config"
    test_config.write_text("[profile e2e]\nregion = us-east-1\n")
    env["AWS_PROFILE"] = "e2e"
    env["AWS_CONFIG_FILE"] = str(test_config)
    resource = boto3.Session(
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    ).resource("dynamodb", endpoint_url=env["AWS_ENDPOINT_URL_DYNAMODB"])
    for name, keys in [("e2e-game", ["pk"]), ("e2e-history", ["pk", "sk"])]:
        resource.create_table(
            TableName=name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": k, "AttributeType": "S"} for k in keys
            ],
            KeySchema=[
                {"AttributeName": k, "KeyType": "HASH" if i == 0 else "RANGE"}
                for i, k in enumerate(keys)
            ],
        )
    history = resource.Table("e2e-history")
    checkpoint = resource.Table("e2e-game")
    # These long scenarios control hand boundaries through the legacy command.
    # Automatic timing itself is covered by AutoDealTests and live UI checks.
    backend_cmd = [
        str(APP_PYTHON), "-c",
        "import main, uvicorn; main.server.auto_deal_delay = 3600; "
        f"uvicorn.run(main.app, host='127.0.0.1', port={api_port})",
    ]
    backend = start(backend_cmd, ROOT / "backend", env, "backend")
    frontend = start(
        [
            "npm",
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(ui_port),
            "--strictPort",
        ],
        ROOT / "frontend",
        env,
        "frontend",
    )
    api = f"http://127.0.0.1:{api_port}"
    url = f"http://127.0.0.1:{ui_port}"
    try:
        await_server(api + "/health", backend)
        await_server(url, frontend)
        with sync_playwright() as pw:
            chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            options = {"executable_path": chrome} if Path(chrome).exists() else {}
            browser = pw.chromium.launch(headless=True, **options)
            contexts = []
            errors = []

            def context():
                c = browser.new_context(viewport={"width": 1440, "height": 1000})
                c.add_init_script(INIT)
                c.on(
                    "page",
                    lambda p: p.on(
                        "pageerror", lambda error: errors.append(str(error))
                    ),
                )
                contexts.append(c)
                return c

            if feedback_only:
                guest = context().new_page()
                guest.goto(url)
                for width, height in [(1440, 1000), (390, 844)]:
                    guest.set_viewport_size({"width": width, "height": height})
                    button = guest.get_by_role("button", name="Feedback", exact=True)
                    expect(button).to_be_in_viewport()
                    button.click()
                    expect(guest.get_by_role("dialog")).to_be_visible()
                    guest.get_by_role("dialog").get_by_label("Reporter name").fill("Guest reporter")
                    guest.get_by_label("Feedback", exact=True).fill("Guest feedback")
                    guest.screenshot(path=str(OUT / f"feedback-{width}.png"))
                    guest.keyboard.press("Escape")
                    expect(button).to_be_focused()
                button.click()
                expect(guest.get_by_label("Feedback", exact=True)).to_have_value("Guest feedback")
                guest.get_by_role("button", name="Send feedback").click()
                expect(guest.get_by_text("Thanks! Your feedback has been saved.")).to_be_visible()
                guest.get_by_role("button", name="Done", exact=True).click()
                player = join(context(), "Feedback player", url)
                player.get_by_role("button", name="Options", exact=True).click()
                player.get_by_role("button", name="Settings", exact=True).click()
                player.get_by_role("button", name="Feedback", exact=True).click()
                player.get_by_label("Reporter name").fill("Spoofed name")
                player.get_by_label("Feedback", exact=True).fill("Player feedback")
                player.get_by_role("button", name="Send feedback").click()
                expect(player.get_by_text("Thanks! Your feedback has been saved.")).to_be_visible()
                records = list(query_records(history, "FEEDBACK"))
                assert len(records) == 2
                assert records[0]["reporter_type"] == "guest"
                assert records[1]["reporter_name"] == "Feedback player"
                assert records[1]["player_id"] == state(player)["you"]
                exported = OUT / "feedback-export.json"
                exported.unlink(missing_ok=True)
                subprocess.run([str(APP_PYTHON), "export_history.py", "--feedback", "--output", str(exported)], cwd=ROOT / "backend", env=env, check=True)
                assert json.loads(exported.read_text()) == records
                assert exported.stat().st_mode & 0o777 == 0o600
                assert not errors, errors
                check("Feedback: desktop/mobile modal, focus, draft, guest/player persistence, settings, private export")
                browser.close()
                return

            ca, cb = context(), context()
            a = join(ca, "E2E Alice", url)
            aid = state(a)["you"]
            expect(a.get_by_role("button", name="Deal first hand")).to_have_count(0)
            b = join(cb, "E2E Bob", url)
            bid = state(b)["you"]
            wait(a, "window.__e2e.state.players.length === 2")
            expect(b.get_by_role("button", name="Deal first hand")).to_have_count(0)
            check("Separate browser identities, shared table, and no manual-deal UI")
            a.get_by_label("Chat message").fill("E2E persistent chat")
            a.get_by_role("button", name="Send", exact=True).click()
            expect(b.get_by_role("log")).to_contain_text("E2E persistent chat")
            check("Chat reaches another player")
            raw(a, {"type": "start"})
            wait(a, "window.__e2e.state.running")
            wait(b, "window.__e2e.state.running")
            expect(a.get_by_label("Two hidden cards")).to_have_count(1)
            expect(b.get_by_label("Two hidden cards")).to_have_count(1)
            check(
                "Private cards: each browser sees its own two cards and opponent backs",
                len(state(a)["hand"]) == 2
                and all("hand" not in p for p in state(a)["players"]),
            )
            a.screenshot(path=str(OUT / "desktop-hand.png"), full_page=True)
            expect(b.get_by_role("button", name="Fold", exact=True)).to_have_count(0)
            a.get_by_role("button", name="Raise", exact=True).click()
            original = state(a)
            a.get_by_role("button", name="All-in", exact=True).click()
            expect(a.get_by_label("Raise to (total chips)")).to_have_value("1000")
            a.get_by_role("button", name="Cancel", exact=True).click()
            check("All-in preset and Cancel do not submit a bet", state(a) == original)
            a.get_by_role("button", name="Raise", exact=True).click()
            a.get_by_label("Raise to (total chips)").press("Escape")
            expect(a.get_by_role("button", name="Raise", exact=True)).to_be_visible()
            a.get_by_role("button", name="Raise", exact=True).click()
            a.get_by_label("Raise to (total chips)").fill("10.5")
            expect(
                a.get_by_role("button", name=re.compile("^Confirm raise"))
            ).to_be_disabled()
            before = state(a)
            raw(b, {"type": "raise", "amount": 80})
            wait(b, "window.__e2e.errors.length > 0")
            check(
                "Out-of-turn API action rejected without changing bets",
                state(b)["pot"] == before["pot"],
            )
            raw(a, {"type": "set_stack", "amount": 9999})
            wait(a, "window.__e2e.errors.length > 0")
            check("Mid-hand chip adjustment rejected", player_stack(a) == 995)
            a.get_by_label("Raise to (total chips)").fill("40")
            a.get_by_role("button", name="Confirm raise 40", exact=True).click()
            wait(b, "window.__e2e.state.target === 40")
            b.get_by_role("button", name="Call 30", exact=True).click()
            wait(a, "window.__e2e.state.street === 'flop'")
            seen = {"flop"}
            by_id = {aid: a, bid: b}
            for _ in range(20):
                s = state(a)
                if not s["running"]:
                    break
                seen.add(s["street"])
                p = by_id[s["actor"]]
                wait(p, "window.__e2e.state.actor === window.__e2e.state.you")
                old = (s["street"], s["actor"])
                p.get_by_role("button", name="Check", exact=True).click()
                wait(
                    a,
                    f"!window.__e2e.state.running || window.__e2e.state.street !== '{old[0]}' || window.__e2e.state.actor !== '{old[1]}'",
                )
            wait(a, "window.__e2e.state.street === 'complete'")
            check(
                "Raise/call/check advances flop, turn, river and showdown",
                seen == {"flop", "turn", "river"},
            )
            check(
                "Completed hand conserves chips",
                sum(p["stack"] for p in state(a)["players"]) == 2000,
            )
            expect(a.locator(".community-cards img")).to_have_count(5)
            check(
                "Showdown exposes both eligible hands",
                len(state(a)["result"]["hands"]) == 2,
            )
            a.screenshot(path=str(OUT / "desktop-showdown.png"), full_page=True)
            a.reload()
            ready(a)
            check(
                "Refresh preserves identity and completed payout",
                state(a)["you"] == aid,
            )
            # Force an actual backend crash while a hand is unfinished.
            stacks = {p["id"]: p["stack"] for p in state(a)["players"]}
            raw(a, {"type": "start"})
            wait(a, "window.__e2e.state.running")
            backend.kill()
            backend.wait(timeout=10)
            backend = start(backend_cmd, ROOT / "backend", env, "backend")
            await_server(api + "/health", backend)
            wait(
                a,
                "window.__e2e.state && !window.__e2e.state.running && window.__e2e.state.street === 'waiting'",
            )
            ready(b)
            check(
                "Crash/restart refunds unfinished hand and reconnects browser identities",
                {p["id"]: p["stack"] for p in state(a)["players"]} == stacks
                and state(a)["you"] == aid,
            )
            # Closing a tab and pruning its seat must not erase the browser's identity.
            b.close()
            wait(
                a,
                f"window.__e2e.state.players.find(p=>p.id==='{bid}').connected === false",
            )
            c = join(context(), "E2E Carla", url)
            wait(a, f"!window.__e2e.state.players.some(p=>p.id==='{bid}')")
            b = join(cb, "E2E Bob", url)
            check(
                "New tab after seat pruning recovers permanent identity",
                state(b)["you"] == bid,
            )
            a.get_by_role("button", name="Options", exact=True).click()
            a.get_by_role("button", name="Leave table", exact=True).click()
            expect(
                a.get_by_role("button", name="Join table", exact=True)
            ).to_be_visible()
            a.get_by_role("button", name="Join table", exact=True).click()
            ready(a)
            check("Leave/rejoin retains browser identity", state(a)["you"] == aid)
            pages = [a, c, b]
            for i in range(6):
                pages.append(join(context(), f"E2E Player {i + 4}", url))
            wait(a, "window.__e2e.state.players.length === 9")
            overflow = context().new_page()
            overflow.goto(url)
            overflow.get_by_label("Your name", exact=True).fill("E2E Tenth")
            overflow.get_by_role("button", name="Join table", exact=True).click()
            expect(overflow.get_by_role("alert")).to_contain_text("full")
            check("Nine-player capacity enforced through UI and server")
            overflow.close()
            for i, p in enumerate(pages):
                set_stack(p, (i + 1) * 50)
            initial_total = sum(p["stack"] for p in state(a)["players"])
            raw(a, {"type": "start"})
            wait(a, "window.__e2e.state.running")
            a.set_viewport_size({"width": 390, "height": 844})
            a.screenshot(path=str(OUT / "mobile-nine-players.png"), full_page=True)
            check(
                "Mobile layout has no horizontal overflow",
                a.evaluate("document.documentElement.scrollWidth <= innerWidth"),
            )
            a.set_viewport_size({"width": 1440, "height": 1000})
            by_id = {state(p)["you"]: p for p in pages}
            for _ in range(30):
                s = state(a)
                if not s["running"]:
                    break
                if s.get("runout_vote"):
                    for pid in s["runout_vote"]["eligible"]:
                        by_id[pid].get_by_role("button", name="Run twice", exact=True).click()
                    wait(a, "window.__e2e.state.street === 'complete'")
                    break
                p = by_id[s["actor"]]
                wait(p, "window.__e2e.state.actor === window.__e2e.state.you")
                if state(p)["can_raise"]:
                    p.get_by_role("button", name=re.compile("^(Bet|Raise)$")).click()
                    p.get_by_role("button", name="All-in", exact=True).click()
                    p.get_by_role("button", name=re.compile("^Confirm (bet|raise) ")).click()
                else:
                    p.get_by_role(
                        "button", name=re.compile("^Call " if state(p)["call_amount"] else "^Check$")
                    ).click()
                old = s["actor"]
                wait(
                    a,
                    f"!window.__e2e.state.running || window.__e2e.state.actor !== '{old}'",
                )
            wait(a, "window.__e2e.state.street === 'complete'")
            check(
                "Nine-player all-in runout settles multiple side pots",
                len(state(a)["result"]["pots"]) > 1,
            )
            check(
                "Side-pot settlement conserves all chips",
                sum(p["stack"] for p in state(a)["players"]) == initial_total,
            )
            a.set_viewport_size({"width": 390, "height": 844})
            a.get_by_role("button", name="Chat & log", exact=True).click()
            a.get_by_label("Chat message").fill("E2E mobile chat")
            a.get_by_role("button", name="Send", exact=True).click()
            expect(b.get_by_role("log")).to_contain_text("E2E mobile chat")
            a.screenshot(path=str(OUT / "mobile-chat.png"), full_page=True)
            check("Mobile chat controls work")
            # Cause a real conditional version conflict in the emulator.
            checkpoint.update_item(
                Key={"pk": "GAME#GLOBAL"},
                UpdateExpression="SET #v = #v + :one",
                ExpressionAttributeNames={"#v": "version"},
                ExpressionAttributeValues={":one": 1},
            )
            raw(a, {"type": "chat", "text": "E2E MUST NOT COMMIT"})
            for _ in range(100):
                if not healthy(api + "/health"):
                    break
                a.wait_for_timeout(50)
            check(
                "Storage conflict stops gameplay and makes health fail",
                not healthy(api + "/health"),
            )
            backend.terminate()
            backend.wait(timeout=10)
            backend = start(backend_cmd, ROOT / "backend", env, "backend")
            await_server(api + "/health", backend)
            ready(a)
            # Inspect persisted data using the production query/export implementations.
            sessions = list(query_records(history, "SESSIONS"))
            session_ids = {e["session_id"] for e in sessions}
            events = [
                e
                for sid in session_ids
                for e in query_records(history, f"SESSION#{sid}")
            ]
            completed = [e for e in events if e["type"] == "hand_completed"]
            cancelled = [e for e in events if e["type"] == "hand_cancelled"]
            check(
                "Archive contains completed hands and exactly one crash cancellation",
                len(completed) == 2 and len(cancelled) == 1,
            )
            check(
                "Failed transaction saved neither chat nor history",
                not any(e.get("text") == "E2E MUST NOT COMMIT" for e in events),
            )
            check(
                "Archived net results balance and exclude rebuys",
                all(sum(e["net"].values()) == 0 for e in completed + cancelled),
            )
            report = player_report(list(query_records(history, f"PLAYER#{aid}")))
            expected = sum(e["net"].get(aid, 0) for e in completed)
            check(
                "Lifetime export matches underlying hand results",
                report["net"] == expected and report["completed_hands"] == 2,
            )
            hand_id = completed[0]["hand_id"]
            hand = list(query_records(history, f"HAND#{hand_id}"))
            check(
                "Hand query retains private cards, deck order and actions",
                any(
                    e["type"] == "hand_started" and len(e["deck_order"]) == 52
                    for e in hand
                )
                and any(e["type"] == "action" for e in hand),
            )
            exported = OUT / "player-export.json"
            subprocess.run(
                [
                    str(APP_PYTHON),
                    "export_history.py",
                    "--player",
                    aid,
                    "--output",
                    str(exported),
                ],
                cwd=ROOT / "backend",
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            exported_report = json.loads(exported.read_text())
            check(
                "Export CLI writes accurate owner-only JSON",
                exported_report["net"] == expected
                and exported.stat().st_mode & 0o777 == 0o600,
            )
            check(
                "Card assets load successfully",
                a.locator("img.card").evaluate_all(
                    "images => images.every(img => img.complete && img.naturalWidth > 0)"
                ),
            )
            check("No browser JavaScript errors", not errors)
            (OUT / "report.json").write_text(
                json.dumps(
                    {
                        "passed": checks,
                        "backend": "real FastAPI/Uvicorn",
                        "browser": "headless Chrome",
                        "storage": "local Moto DynamoDB emulator",
                        "live_aws_mutated": False,
                    },
                    indent=2,
                )
            )
            browser.close()
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
        emulator.stop()
        for log in logs:
            log.close()


if __name__ == "__main__":
    run(feedback_only="--feedback-only" in sys.argv)
