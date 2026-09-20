# Operations: hosting and verification

[Architecture overview](../architecture.md)

The UI and backend are served separately. One backend process owns the live
table; optional DynamoDB storage provides restart recovery and permanent history. Setup and deployment
commands live in the [README](../../README.md).

## Serving the app

The frontend is a static Vite build; FastAPI runs separately under Uvicorn.
The browser reaches the backend through a WebSocket-capable proxy or a configured
backend address. Gameplay and private feedback use separate connections to the
same backend. HTTPS pages use secure WebSockets. During development, the
[Vite configuration](../../frontend/vite.config.ts) provides the proxy.

The backend's environment selects its database tables and supplies its AWS
authentication. [Storage initialization](../../backend/storage.py) enables
persistence only when configured. Without it, gameplay runs in memory and
feedback is rejected. A healthy HTTP endpoint alone does not prove storage is
enabled; deployment verification must include a saved record.

Run **one backend worker**. The module-level
[GameServer](../../backend/main.py) owns the shared live table; separate workers
would create conflicting games. With persistence enabled, restarts recover
saved state. Rooms and distributed coordination are not implemented.

See the [README](../../README.md#hosting-and-current-limits) for deployment settings
and commands.

## Storage infrastructure

The [DynamoDB template](../../infra/dynamodb.yaml) provisions a bounded checkpoint
table and a growing history table. Capacity is fixed, with more write capacity
allocated to history. Transactions and duplicated query records increase write
consumption; exhausted capacity can throttle saves and stop play. Both tables
have deletion protection and are retained on infrastructure deletion or
replacement. History has no expiry; point-in-time backups are not enabled.

The [backend access template](../../infra/render-access.yaml) defines a dedicated
IAM identity that can read and write individual items on these two tables.
Its credential is supplied only to the backend, independently of developer
authentication. Browsers receive no AWS access. Authorized offline exports use
separate access to query private history.

Each environment needs its own tables and one backend writer. Local development
uses memory-only mode or an isolated database emulator; running two backends
against the same checkpoint would trigger the version guard and stop play.
See [persistence](persistence.md) for recovery, migration, and failure behavior.

## Cost monitoring

The [budget template](../../infra/budgets.yaml) monitors project-tagged spending
and account-wide DynamoDB spending. Alerts exclude credits and refunds so those
do not hide usage charges. These notifications do not cap spending or stop
services. Thresholds live in the template; setup and pricing references live in
the [README](../../README.md#dynamodb-and-budget-alerts).

## Verification workflow

[Engine tests](../../backend/tests/test_game.py) cover the game rules and privacy.
[Runout tests](../../backend/tests/test_runouts.py) exercise unanimous consent,
one-run fallback, timer cancellation, card integrity, side-pot accounting and
restart/reconnect behavior.
[API tests](../../backend/tests/test_api.py) exercise the WebSocket contract,
sessions, invalid messages, and the single shared game using in-process clients.
[Feedback tests](../../backend/tests/test_feedback.py) cover private persistence, reporter
attribution, validation, and failures without AWS access.
[Persistence tests](../../backend/tests/test_storage.py) cover recovery and storage
failure behavior without AWS access. CloudFormation templates are checked with
`cfn-lint`; live deployment is verified through stack events and table/budget
descriptions. [GitHub Actions](../../.github/workflows/checks.yml) runs the backend
suite and frontend clean-install/lint/build checks on pushes and pull requests.
The frontend [npm configuration](../../frontend/.npmrc) enables normal peer-dependency
resolution, overriding user-level legacy settings. Validate the committed lockfile
with `npm ci` before lint/build so local dependency checks match CI.
[History tests](../../backend/tests/test_history.py) validate event capture,
identity, accounting, migration, and transactional failure behavior offline.

[Browser E2E tests](../../backend/e2e/browser_test.py) run the real Vite frontend
and Uvicorn backend through Playwright/Chrome, backed by a separate Moto DynamoDB
server. Each player has an isolated browser profile. The test runner strips AWS
settings, supplies fake credentials and a loopback DynamoDB endpoint, and uses
separate temporary ports, so it does not write to the deployed game or history.
The `--feedback-only` mode checks desktop/mobile dialogs, focus restoration, draft
retention, guest/player persistence, Settings access, and private feedback export.
Backend subprocesses keep their normal production dependencies. Tests cover
complete hands, nine-player side pots, browser identity, private cards, crash
recovery, transaction conflicts, mobile interactions, and the private export CLI.
Artifacts go to ignored `.artifacts/e2e/`; services stop after the run. The emulator
does not reproduce AWS IAM, billing, throttling, or service latency, and mobile
viewports do not replace physical-device testing. Setup is in the
[README](../../README.md#browser-end-to-end-tests).

UI verification uses a separate memory-only backend (`DYNAMODB_TABLE` empty)
and an explicitly configured development WebSocket URL. Compare reference and
local screenshots at matching CSS viewport dimensions; check sparse and full
tables, showdown card spacing, controls, chat, and reconnects. Browser viewport
overrides may be affected by zoom, so verify `innerWidth` and `innerHeight`.
The PokerNow public tutorial supplies visual references but does not expose all
live-game controls or mobile keyboard behavior; those require a live reference
and device validation before claiming exact parity.

The browser E2E runners extend the deal timer for deterministic seating and
recovery scenarios and use the legacy start command at controlled boundaries.
[Settings tests](../../backend/tests/test_settings.py) verify automatic first and
subsequent deals, eligibility, cancellation, and persistence-failure guards.

## Keeping this guide current

This guide describes the implemented system. The Excalidraw files in
[`diagrams/`](../../diagrams/) are original design sketches and may differ from it.
[AGENTS.md](../../AGENTS.md) requires reviewing architecture documentation with each
code change and updating affected explanations in the same change. Keep the
overview conceptual and implementation details in the relevant module page.
CI does not automatically verify documentation accuracy.
