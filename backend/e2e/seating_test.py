"""Isolated browser checks for seating; runs without persistence or live game data."""
import os
from pathlib import Path
import subprocess
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".artifacts" / "seating"
OUT.mkdir(parents=True, exist_ok=True)


def run():
    env = {**os.environ, "DYNAMODB_TABLE": "", "DYNAMODB_HISTORY_TABLE": "",
           "VITE_WS_URL": "ws://127.0.0.1:18800/ws"}
    processes = []
    logs = []
    contexts = []
    try:
        for name, command, cwd in [
            ("backend", [str(ROOT / "backend/venv/bin/python"), "-m", "uvicorn", "main:app", "--port", "18800"], ROOT / "backend"),
            ("frontend", ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "15173", "--strictPort"], ROOT / "frontend"),
        ]:
            log = (OUT / (name + ".log")).open("w")
            logs.append(log)
            processes.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log))
        for url in ["http://127.0.0.1:18800/health", "http://127.0.0.1:15173"]:
            for _ in range(100):
                assert all(p.poll() is None for p in processes), "Test service failed to start"
                try:
                    urllib.request.urlopen(url, timeout=1).close()
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise AssertionError("Test service did not start")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome", headless=True)
            pages = []
            for name in ["Alice", "Bob", "Charlie", "Dana", "Eli", "Fran", "Grace", "Henry"]:
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                contexts.append(context)
                page = context.new_page()
                page.goto("http://127.0.0.1:15173")
                page.get_by_label("Your name", exact=True).fill(name)
                page.get_by_role("button", name="Join table", exact=True).click()
                expect(page.get_by_role("button", name="Player options for " + name, exact=True)).to_be_visible()
                pages.append(page)
            a, b = pages[:2]
            for width, height in [(1440, 900), (390, 844)]:
                a.set_viewport_size({"width": width, "height": height})
                a.get_by_role("button", name="Player options for Alice", exact=True).click()
                modal = a.get_by_role("dialog")
                modal.get_by_label("Your stack", exact=True).fill("")
                expect(modal.get_by_role("button", name="Set stack", exact=True)).to_be_disabled()
                modal.get_by_label("Your stack", exact=True).fill(str(width))
                a.screenshot(path=str(OUT / f"stack-{width}.png"))
                modal.get_by_role("button", name="Set stack", exact=True).click()
                expect(modal).not_to_be_visible()
                expect(a.get_by_role("button", name="Player options for Alice", exact=True)).to_contain_text(f"{width:,}")
                expect(b.get_by_role("button", name="Player options for Alice", exact=True)).to_contain_text(f"{width:,}")
                a.get_by_role("button", name="Player options for Alice", exact=True).click()
                expect(modal.get_by_label("Your stack", exact=True)).to_have_value(str(width))
                modal.get_by_label("Your stack", exact=True).fill("999")
                modal.get_by_role("button", name="Cancel", exact=True).click()
                a.get_by_role("button", name="Player options for Alice", exact=True).click()
                expect(modal.get_by_label("Your stack", exact=True)).to_have_value(str(width))
                a.keyboard.press("Escape")
                a.get_by_role("button", name="Seat 9", exact=True).click()
                expect(a.get_by_role("button", name="Seat 1", exact=True)).to_be_enabled()
                a.reload()
                expect(a.get_by_role("button", name="Seat 1", exact=True)).to_be_enabled()
                a.get_by_role("button", name="Player options for Bob", exact=True).click()
                expect(a.get_by_role("dialog")).to_be_visible()
                a.screenshot(path=str(OUT / f"dialog-{width}.png"))
                a.get_by_role("button", name="Cancel", exact=True).click()
                expect(b.get_by_role("button", name="Player options for Bob", exact=True)).to_be_visible()
                a.screenshot(path=str(OUT / f"table-{width}.png"))
                assert a.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Horizontal overflow"
                assert a.evaluate("document.documentElement.scrollHeight <= innerHeight"), "Vertical overflow"
                boxes = [el.bounding_box() for el in a.locator(".table-seat").all()]
                for box in boxes:
                    assert box and box["x"] >= 0 and box["y"] >= 0
                    assert box["x"] + box["width"] <= width
                    assert box["y"] + box["height"] <= height
                a.get_by_role("button", name="Seat 1", exact=True).click()
                expect(a.get_by_role("button", name="Seat 9", exact=True)).to_be_enabled()
                print(f"PASS: seat move, reload, dialog, cancel, bounds at {width}x{height}", flush=True)
            a.get_by_role("button", name="Player options for Bob", exact=True).click()
            a.get_by_role("button", name="Kick player", exact=True).click()
            expect(b.get_by_role("heading", name="Join the table", exact=True)).to_be_visible()
            expect(b.get_by_role("alert")).to_contain_text("removed")
            expect(a.get_by_role("button", name="Seat 2", exact=True)).to_be_enabled()
            b.wait_for_timeout(1500)
            expect(b.get_by_role("heading", name="Join the table", exact=True)).to_be_visible()
            b.get_by_role("button", name="Join table", exact=True).click()
            expect(b.get_by_role("button", name="Player options for Bob", exact=True)).to_be_visible()
            print("PASS: kick closes peer, frees seat, stops reconnect, permits manual rejoin", flush=True)
            a.get_by_role("button", name="Deal first hand", exact=True).click()
            expect(a.get_by_role("button", name="Seat 9", exact=True)).to_be_disabled()
            a.get_by_role("button", name="Player options for Bob", exact=True).click()
            expect(a.get_by_role("button", name="Kick player", exact=True)).to_be_disabled()
            a.get_by_role("button", name="Cancel", exact=True).click()
            for width, height in [(1440, 900), (390, 844)]:
                a.set_viewport_size({"width": width, "height": height})
                a.screenshot(path=str(OUT / f"hand-{width}.png"))
                assert a.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert a.evaluate("document.documentElement.scrollHeight <= innerHeight")
            a.get_by_role("button", name="Player options for Alice", exact=True).click()
            expect(a.get_by_role("dialog").get_by_label("Your stack", exact=True)).to_be_disabled()
            expect(a.get_by_role("dialog").get_by_role("button", name="Set stack", exact=True)).to_be_disabled()
            print("PASS: own-player stack editing, broadcast, cancel/reset, and live-hand restriction", flush=True)
            print("PASS: active hand disables moving and kicking; live layout at both sizes", flush=True)
            browser.close()
    finally:
        for proc in reversed(processes):
            proc.terminate()
            proc.wait(timeout=10)
        for log in logs:
            log.close()


if __name__ == "__main__":
    run()
