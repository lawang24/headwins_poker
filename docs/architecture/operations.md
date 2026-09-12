# Operations: hosting and verification

[Architecture overview](../architecture.md)

The UI and backend are served separately. One backend process owns the live
table; optional DynamoDB storage provides restart recovery. Setup and deployment
commands live in the [README](../../README.md).

## Serving the app

During development, Vite proxies `/ws` and `/health` to the backend on port 8000.
The frontend normally derives the WebSocket address from the page's host and
protocol; `VITE_WS_URL` can override it.

For production, serve the Vite build as static files and proxy `/ws` to Uvicorn
with WebSocket upgrade support, or configure an explicit backend URL at build
time. HTTPS pages use secure WebSockets (`wss://`). The frontend and backend are
separate serving concerns; FastAPI does not serve the built UI.

Run **one backend worker**. The module-level `GameServer` contains a single
live table, and separate workers would create conflicting games. With DynamoDB
enabled, restarts recover durable checkpoints as described above; memory-only
mode still loses all state. Rooms, long-term hand archives, distributed
coordination, and real-money settlement are not implemented.

See the [project README](../../README.md) for setup commands and hosting limits.

## Storage infrastructure

The [DynamoDB template](../../infra/dynamodb.yaml) provisions the checkpoint table.
It uses Standard class with fixed 5 RCU / 25 WCU. No autoscaling, paid backups,
global replicas, or customer-managed KMS keys are enabled. Capacity exhaustion
can throttle saves; it does not increase provisioned capacity automatically.
Table deletion is protected and CloudFormation retains the table on deletion
or replacement. Storage is a single bounded checkpoint.

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
[Persistence tests](../../backend/tests/test_storage.py) cover recovery and storage
failure behavior without AWS access. CloudFormation templates are checked with
`cfn-lint`; live deployment is verified through stack events and table/budget
descriptions. [GitHub Actions](../../.github/workflows/checks.yml) runs the backend
suite and frontend lint/build checks on pushes and pull requests.

## Local developer tooling

The local development environment also has Agent Toolkit for AWS installed: AWS
CLI browser authentication, global AWS skills, and an AWS MCP connection for
Codex. The MCP connection uses the named `lawang` CLI profile; toolkit services
use `us-east-1`. This is developer tooling, not an application dependency or a
deployed service. The backend's boto3 connection is independent of the MCP tooling;
[run.py](../../backend/run.py) loads ignored local `.env` settings for development.
Production should supply environment settings and an IAM workload role with
`dynamodb:GetItem` and `dynamodb:PutItem` scoped to the table ARN. AWS guidance in
[AGENTS.md](../../AGENTS.md) supplements the project rules; credentials and MCP
configuration remain outside the repository.

## Keeping this guide current

This guide describes the implemented system. The Excalidraw files in
[`diagrams/`](../../diagrams/) are original design sketches and may differ from it.
[AGENTS.md](../../AGENTS.md) requires reviewing architecture documentation with each
code change and updating affected explanations in the same change. Keep the
overview conceptual and implementation details in the relevant module page.
CI does not automatically verify documentation accuracy.
