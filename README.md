# Headwins Poker

One global play-money, no-limit Texas Hold’em game for 2–9 players. React/TypeScript renders the table; FastAPI owns the rules and sends each player a private WebSocket view.

## Run locally

Requirements: Python 3.12 and Node.js 22.12 or later.

In one terminal:

```sh
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173/ in two separate browser profiles (or different browsers) and enter a name in each. Tabs in the same profile reuse one player identity. Everyone connects to the same global game. Any connected player can deal once two players have chips. The **Invite friends** button copies the app URL.

Vite proxies `/ws` to port 8000. To use another backend address, copy `frontend/.env.example` to `frontend/.env.development.local` and set `VITE_WS_URL` (for example, `ws://127.0.0.1:8001/ws`), then run Uvicorn on that port. A localhost invitation works only on the same machine; remote friends need a reachable hosted address.

### Running alongside another app on port 8000

The local poker configuration uses port 8001 when port 8000 is occupied. Start
its backend from `backend` with:

```sh
./venv/bin/uvicorn main:app --host 127.0.0.1 --port 8001 --env-file .env
```

Set `VITE_WS_URL=ws://127.0.0.1:8001/ws` in the ignored
`frontend/.env.development.local` and run the frontend normally. Check the backend
at `http://127.0.0.1:8001/health`; Vite's default health proxy still targets 8000.
`python run.py` continues to use the default port 8000.

## Gameplay

- Start with 1,000 play chips; blinds are 5/10. You can change your own stack between hands, including rebuying after losing your chips.
- The dealer rotates between eligible players. Heads-up, the dealer posts the small blind and acts first preflop, last postflop.
- **Raise to** is the total committed on the current betting street. The server checks turns, minimum raises, available chips, and whether short all-ins reopen betting.
- All-in players skip further actions. When no further betting is possible, the board runs out automatically. Main/side pots split by eligibility and hand rank; odd chips go clockwise starting left of the dealer. Uncalled excess is returned.
- A completed hand stays visible for review. The host deals the next hand. There is no mid-hand restart.
- New arrivals wait for the next hand. Disconnecting folds a player with chips; an all-in player remains eligible. Reload restores the same seat using its saved browser identity, but a hand already folded remains folded. Reconnecting the same token elsewhere replaces the old socket.
- Chat and the last 100 activity messages are shared by everyone at the table. Hole cards stay private until a contested showdown.

## DynamoDB and budget alerts

The local `backend/.env` selects the checkpoint and history tables and the AWS
region/profile. `python run.py` loads that ignored file. On a fresh checkout,
copy `backend/.env.example` to `backend/.env` after deploying both tables, then
set `DYNAMODB_TABLE` and `DYNAMODB_HISTORY_TABLE` from your stack outputs.
For direct Uvicorn use, add `--env-file .env` from the backend directory.
Leave `DYNAMODB_TABLE` empty for memory-only development and automated tests.
Never put AWS credentials into frontend environment files.

The backend atomically saves its checkpoint and permanent game history before
acknowledging changes. History includes sessions, identities, chip movements,
every accepted action/chat entry, hole cards, full shuffled deck order, boards,
and hand results. The browser keeps its random identity credential across visits;
seat removal does not delete that player's history. Clearing browser storage loses
access to the identity; cross-device accounts are not implemented.

Sessions start on the first join and end when everyone disconnects or the backend
restarts. Reconnects within a session preserve retained stacks; pruned seats start
at 1,000 again with that entry recorded separately from winnings. On recovery,
unfinished hands are cancelled and contributions refunded; completed payouts
remain intact. Schema 1 checkpoints migrate on startup, preserving retained player
IDs and a baseline of available data. Older actions cannot be reconstructed, and
old backend versions cannot read the resulting schema 2 checkpoint. If DynamoDB fails, the
backend stops play and returns HTTP 503 on `/health`; fix connectivity/access and
restart it. No unsaved game is allowed to continue.

Infrastructure is reproducible from the repository root:

```sh
aws cloudformation deploy --profile lawang --region us-east-1 \
  --stack-name headwins-poker-budget --template-file infra/budgets.yaml \
  --parameter-overrides AlertEmail=YOUR_EMAIL
aws cloudformation deploy --profile lawang --region us-east-1 \
  --stack-name YOUR_DATA_STACK --template-file infra/dynamodb.yaml
```

Both tables are tagged `Project=headwins-poker` and use Standard provisioned
capacity: **5 RCU / 5 WCU** for checkpoints and **5 RCU / 20 WCU** for history.
There is no autoscaling or paid backup configuration. Updating the stack retains
the existing checkpoint table, reduces its write capacity, and adds the archive.
AWS documents an always-free allowance of 25 RCU, 25 WCU, and 25 GB; this allowance
is shared with other eligible account usage. The archive grows with play, and transactions plus copied query records consume
more writes than the original checkpoint-only implementation. Heavy activity can
throttle saves; retained history is not a backup.
[DynamoDB free-tier documentation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html).

Two free monitoring budgets alert when recorded monthly costs exceed **$0.01**:
`headwins-poker-budget-project` covers the project tag, and
`headwins-poker-budget-dynamodb` covers all DynamoDB costs, including the period
before AWS discovers the tag. Credits and refunds are excluded. **Budgets do not
cap spending**, and billing/notifications are delayed; they cannot guarantee a
$0 bill. [Budget considerations](https://docs.aws.amazon.com/cost-management/latest/userguide/bcm-lite-use-budget.html).

After AWS exposes `Project` under Billing cost allocation tags (this can take
24 hours), activate it:

```sh
aws ce update-cost-allocation-tags-status --profile lawang --region us-east-1 \
  --cost-allocation-tags-status TagKey=Project,Status=Active
```

For deployment on AWS, omit `AWS_PROFILE` and attach a workload IAM role granting
only `dynamodb:GetItem` and `dynamodb:PutItem` on both table ARNs. Transaction
writes are authorized through the underlying item actions. Give authorized offline
analysts `dynamodb:Query` on the history table. Keep one backend worker. Both tables
have deletion protection and CloudFormation retention enabled;
removing the stack alone does not delete saved data.

## Exporting history

After deploying the updated stack, configuring both table names, and restarting
the backend, run these commands from `backend` using an authorized AWS profile:

```sh
./venv/bin/python export_history.py --sessions --output /tmp/poker-sessions.json
./venv/bin/python export_history.py --session SESSION_ID --output /tmp/poker-session.json
./venv/bin/python export_history.py --hand HAND_ID --output /tmp/poker-hand.json
./venv/bin/python export_history.py --player PLAYER_ID --output /tmp/poker-player.json
./venv/bin/python export_history.py --system --output /tmp/poker-system.json
./venv/bin/python export_history.py --feedback --output /tmp/poker-feedback.json
```

Session events identify players and hands. Player exports include lifetime net
chips and totals by session, calculated from payouts minus contributions; rebuys,
stack changes, and cash-outs are separate movement records. Cancelled hands count
as zero net. Each output must be a new filename and is created with owner-only
permissions. Hand/session exports include private cards and deck order, so keep
them outside the repository and away from live players. The CLI loads the local
backend `.env`; it does not change game state. Equity calculation and a history UI
are future work; the necessary card/action data is now recorded.

## Checks

```sh
cd backend
./venv/bin/python -m unittest discover -s tests -v
```

```sh
cd frontend
npm ci
npm run lint
npm run build
```

GitHub Actions runs the backend regression suite and frontend lint/build on pushes and pull requests. Tests cover complete hands, turn order, invalid requests, private cards, chip accounting, folded players, all-ins, ties, side pots, disconnects, sessions, the single shared game, and randomized legal play.

### Seating checks

Click an empty numbered seat to move, or a player's nameplate to open the kick
confirmation. Anyone seated can remove another player. Both actions are available
between hands. Kicking cashes out the player and returns them to the join screen;
they can join again manually.

After installing the browser test dependencies below, run the isolated seating check:

```sh
PYTHONPATH=.artifacts/e2e/deps backend/venv/bin/python backend/e2e/seating_test.py
```

It uses local ports 18800 and 15173, in-memory game state, and disposable Chrome
profiles. It checks moving, reconnecting, kicking, live-hand restrictions, and
desktop/mobile layouts; screenshots go to `.artifacts/seating/`.

### Browser end-to-end tests

After installing the normal backend and frontend dependencies, run from the
repository root:

```sh
backend/venv/bin/python -m pip install --upgrade --target .artifacts/e2e/deps -r backend/e2e/requirements.txt
PYTHONPATH=.artifacts/e2e/deps backend/venv/bin/python backend/e2e/browser_test.py
```

The runner uses installed Google Chrome on macOS, or Playwright Chromium elsewhere
(install it with `PYTHONPATH=.artifacts/e2e/deps backend/venv/bin/python -m playwright install chromium`).
It starts the real frontend and backend on temporary ports, with a local Moto
DynamoDB emulator and disposable browser profiles. AWS credentials and endpoints
are explicitly isolated; no live game data is changed. Backend and export
subprocesses use the existing `backend/venv` production dependencies, with the
test package path removed from their environment.

Coverage includes browser identity, chat, card privacy, rejected actions, a full
hand, all-ins/side pots with nine players, mobile layout/chat, process-crash recovery,
conditional-write failure, and permanent history/profit exports. Screenshots,
logs, and the passing-check report are written to the ignored `.artifacts/e2e/`
directory. Test services shut down on completion. This is Chromium browser testing
with mobile viewport simulation, not a physical-phone or real-AWS load test.

## Structure

- [Architecture guide](docs/architecture.md): a short system overview with focused module pages for implementation details. [AGENTS.md](AGENTS.md) requires keeping it current with relevant code changes.
- `backend/game.py`: synchronous game rules and serializable player views.
- `backend/main.py`: WebSocket protocol, the game lock, sessions, bounded broadcasts, and `/health`.
- `backend/storage.py`: atomic DynamoDB checkpoints/history and restart recovery.
- `backend/archive.py`: private event schema, query records, and paginated reads.
- `backend/export_history.py`: authorized offline exports and player net-chip totals.
- `infra/`: CloudFormation table and monitoring budgets.
- `backend/tests/`: engine and in-process WebSocket integration tests.
- `frontend/src/App.tsx`: name entry, connection recovery, table, actions, and chat.
- `diagrams/`: original design sketches; the architecture guide describes the implemented system.

## Hosting and current limits

Build the frontend with `npm run build` and serve `frontend/dist`. Proxy `/ws` to Uvicorn with WebSocket upgrade support, or supply an explicit `VITE_WS_URL` at build time. HTTPS pages require `wss://` connections. Run **one backend worker**: live gameplay is not coordinated between processes. `/health` returns `{"status":"ok"}` unless a persistence failure has stopped the game.

This implementation is for casual play-money games. Memory-only mode loses state on restart; DynamoDB mode recovers the saved table. Everyone who opens the app joins the same game; there is no room selection, password, or account system. Account authentication, a history/equity UI, distributed workers, and public-service abuse controls are separate work; no real-money settlement is implemented.

### Feedback

Production uses the Netlify frontend at `https://larrypokernow.netlify.app` and
the Render backend at `https://headwins-poker.onrender.com`. Set the frontend's
`VITE_WS_URL` to `wss://headwins-poker.onrender.com/ws` when building it. The
Render backend needs these environment settings (its Uvicorn command does not
load the local `.env`):

| Setting | Value |
| --- | --- |
| `DYNAMODB_TABLE` | Checkpoint table name from your data stack outputs |
| `DYNAMODB_HISTORY_TABLE` | History table name from your data stack outputs |
| `AWS_REGION` | `us-east-1` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Dedicated backend credential, stored only in Render |

Provision the backend identity separately from the retained data tables:

```sh
aws cloudformation deploy --profile lawang --region us-east-1 \
  --stack-name headwins-poker-render-access \
  --template-file infra/render-access.yaml --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides DataStackName=YOUR_DATA_STACK
```

Create an access key for the resulting backend user and transfer it securely to
Render without printing it or committing it. Preserve existing Render variables
when configuring the service, then redeploy. Verify `/health`, submit a labeled
feedback report, and confirm the report appears in the history export. A healthy
HTTP endpoint alone does not prove storage is enabled. Use separate tables or the
emulator for local development while production owns these tables.

The corner Feedback button is available before joining, at the table, and in
Settings. Reports are stored privately in `DYNAMODB_HISTORY_TABLE`, with a server
UTC timestamp, name, and stable player ID for returning players. Guests provide
a self-reported name. Both DynamoDB settings must be configured; memory-only mode
returns an error and preserves the draft. Restart the backend after updating code.
When serving behind a reverse proxy, enable WebSocket upgrades for `/feedback`
as well as `/ws`. `VITE_WS_URL` should end in `/ws`; feedback uses the same host
and path prefix with `/feedback`. Use the `--feedback` export above to review reports.
Run the focused browser check with
`PYTHONPATH=.artifacts/e2e/deps backend/venv/bin/python backend/e2e/browser_test.py --feedback-only`
from the repository root after installing the E2E dependencies.
