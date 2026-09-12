# Operations: hosting and verification

[Architecture overview](../architecture.md)

The UI and backend are served separately. One backend process owns the live
table; optional DynamoDB storage provides restart recovery and permanent history. Setup and deployment
commands live in the [README](../../README.md).

## Serving the app

During development, Vite proxies `/ws`, `/feedback`, and `/health` to the backend on port 8000.
The frontend normally derives the WebSocket address from the page's host and
protocol; `VITE_WS_URL` can override it.

The current local configuration points `VITE_WS_URL` at poker's backend on
port 8001 so a separate app can retain port 8000. Uvicorn is launched with an
explicit port and the backend `.env`; the default `run.py` launcher and Vite
health proxy still target 8000. Verify poker directly at port 8001. See the
[README](../../README.md#running-alongside-another-app-on-port-8000) for commands.

For production, serve the Vite build as static files and proxy `/ws` and `/feedback` to Uvicorn
with WebSocket upgrade support, or configure an explicit backend URL at build
time. HTTPS pages use secure WebSockets (`wss://`). The frontend and backend are
separate serving concerns; FastAPI does not serve the built UI.

Production serves the frontend at [larrypokernow.netlify.app](https://larrypokernow.netlify.app)
and one Render backend at [headwins-poker.onrender.com](https://headwins-poker.onrender.com).
The frontend's build-time WebSocket URL targets Render directly for both `/ws`
and `/feedback`. Render starts Uvicorn in `backend/`; it does not load the local
developer `.env`. Its backend environment selects the existing game and history
tables in `us-east-1` and supplies a dedicated AWS access key. Without
`DYNAMODB_TABLE`, the server starts in memory-only mode and rejects feedback,
even though `/health` returns OK. Verify an actual saved record after deployment.

Run **one backend worker**. The module-level `GameServer` contains a single
live table, and separate workers would create conflicting games. With DynamoDB
enabled, restarts recover durable checkpoints as described above; memory-only
mode still loses all state. Rooms, distributed coordination, equity analysis, account login, and real-money
settlement are not implemented. Private hand archives and player result exports
are available when both DynamoDB tables are configured.

See the [project README](../../README.md) for setup commands and hosting limits.

## Storage infrastructure

The [DynamoDB template](../../infra/dynamodb.yaml) provisions a checkpoint table
(5 RCU / 5 WCU) and an archive table (5 RCU / 20 WCU), both Standard provisioned
capacity. Total configured capacity is 10 RCU / 25 WCU, with no autoscaling,
paid backups, global replicas, or customer-managed KMS keys. This preserves the
existing fixed write-capacity budget while moving most writes to history.
Transactions and duplicated query records increase write consumption; capacity
exhaustion can throttle saves and stop play rather than automatically adding cost.
Archive storage grows indefinitely. Retention is not a backup: point-in-time
recovery is explicitly disabled to preserve this project's budget-conscious setup.
For irreplaceable production history, enable backups and add throttle/error alarms
as an operational follow-up with its own cost review.

Both tables have deletion protection and CloudFormation retention on deletion or
replacement. Updating the stack adds the history table without replacing the old
checkpoint table, and reduces checkpoint write capacity from 25 to 5. Deploy the
template first, set `DYNAMODB_HISTORY_TABLE`, grant the backend access to both
tables, then restart the new backend. The first save upgrades the checkpoint;
old binaries do not support schema 2. The source change itself does not activate
history on an already-running deployment.

Production uses `headwins-poker-data-game` and `headwins-poker-data-history`
in `us-east-1`. The [Render access template](../../infra/render-access.yaml)
owns a dedicated IAM user in the `headwins-poker-render-access` stack. Its only
permissions are `dynamodb:GetItem` and `dynamodb:PutItem` on these two tables,
including the item actions used by transactions. It has no console login,
table administration, bulk scan/query, deletion, or access to unrelated resources.
The access key is managed outside CloudFormation and stored in Render's backend
environment; it is never an infrastructure output or a frontend setting.
Rotate by installing a second key in Render, redeploying and verifying persistence,
then deactivating and removing the old key. Render-managed OIDC is a future
alternative if the workspace has an eligible plan.

Earlier local development used these same tables with the `lawang` developer
login. Do not run a local backend against them while production is active: the
single-writer checkpoint version guard would stop one of the processes. Use
memory-only mode or the isolated DynamoDB emulator for local work. Renewing a
developer login does not change Render's separate workload credential.

## Cost monitoring

The [budget template](../../infra/budgets.yaml) defines two monitoring budgets.
Both monitoring budgets alert above $0.01/month, excluding credits and refunds
so credits do not hide usage charges. One filters `Project=headwins-poker`; the
other covers all Amazon DynamoDB spending while tag-based billing becomes
available. The project tag must be activated as a cost allocation tag after AWS
discovers it. Budgets are delayed notifications, not spending caps. Free-tier
eligibility and account-wide usage still determine charges; a zero bill is not
guaranteed. See the README for deployment, activation, and verification commands.

See the [README](../../README.md#dynamodb-and-budget-alerts) for free-tier context,
pricing references, and deployment, activation, and verification commands.

## Verification workflow

[Engine tests](../../backend/tests/test_game.py) cover the game rules and privacy.
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

## Local developer tooling

The local development environment also has Agent Toolkit for AWS installed: AWS
CLI browser authentication, global AWS skills, and an AWS MCP connection for
Codex. The MCP connection uses the named `lawang` CLI profile; toolkit services
use `us-east-1`. This is developer tooling, not an application dependency or a
deployed service. The backend's boto3 connection is independent of the MCP tooling;
[run.py](../../backend/run.py) loads ignored local `.env` settings for development.
The production identity supplies environment settings and has
`dynamodb:GetItem` and `dynamodb:PutItem` scoped to both table ARNs. DynamoDB
transaction permissions use the underlying item actions; there is no standalone
`dynamodb:TransactWriteItems` IAM action. Authorized offline exports additionally
need `dynamodb:Query` on the history table. See [AWS transaction IAM guidance](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis-iam.html).
Browsers receive no AWS access. AWS guidance in
[AGENTS.md](../../AGENTS.md) supplements the project rules; credentials and MCP
configuration remain outside the repository.

## Keeping this guide current

This guide describes the implemented system. The Excalidraw files in
[`diagrams/`](../../diagrams/) are original design sketches and may differ from it.
[AGENTS.md](../../AGENTS.md) requires reviewing architecture documentation with each
code change and updating affected explanations in the same change. Keep the
overview conceptual and implementation details in the relevant module page.
CI does not automatically verify documentation accuracy.
