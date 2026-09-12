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

Open http://127.0.0.1:5173/ in two separate tabs and enter a name in each. Everyone connects to the same global game. The first connected player is the host and can deal once two players have chips. The **Invite friends** button copies the app URL.

Vite proxies `/ws` to port 8000. To use another backend address, copy `frontend/.env.example` to `frontend/.env.development.local` and set `VITE_WS_URL` (for example, `ws://127.0.0.1:8001/ws`), then run Uvicorn on that port. A localhost invitation works only on the same machine; remote friends need a reachable hosted address.

## Gameplay

- Start with 1,000 play chips; blinds are 5/10. You can change your own stack between hands, including rebuying after losing your chips.
- The dealer rotates between eligible players. Heads-up, the dealer posts the small blind and acts first preflop, last postflop.
- **Raise to** is the total committed on the current betting street. The server checks turns, minimum raises, available chips, and whether short all-ins reopen betting.
- All-in players skip further actions. When no further betting is possible, the board runs out automatically. Main/side pots split by eligibility and hand rank; odd chips go clockwise starting left of the dealer. Uncalled excess is returned.
- A completed hand stays visible for review. The host deals the next hand. There is no mid-hand restart.
- New arrivals wait for the next hand. Disconnecting folds a player with chips; an all-in player remains eligible. Reload restores the same seat using a tab-scoped session token, but a hand already folded remains folded. Reconnecting the same token elsewhere replaces the old socket. The host role passes to the first connected seat.
- Chat and the last 100 activity messages are shared by everyone at the table. Hole cards stay private until a contested showdown.

## DynamoDB and budget alerts

The local `backend/.env` selects `headwins-poker-data-game` in `us-east-1`
using AWS profile `lawang`. `python run.py` loads that ignored file. On a fresh
checkout, copy `backend/.env.example` to `backend/.env` after deploying the table.
For direct Uvicorn use, add `--env-file .env` from the backend directory.
Leave `DYNAMODB_TABLE` empty for memory-only development and automated tests.
Never put AWS credentials into frontend environment files.

The backend saves seats, tokens, chips, and the last 100 activity entries before
acknowledging changes. On recovery, unfinished hands are cancelled and committed
chips returned; completed payouts remain intact. Existing seat-pruning rules still
apply, so this is not a permanent player-account system. If DynamoDB fails, the
backend stops play and returns HTTP 503 on `/health`; fix connectivity/access and
restart it. No unsaved game is allowed to continue.

Infrastructure is reproducible from the repository root:

```sh
aws cloudformation deploy --profile lawang --region us-east-1 \
  --stack-name headwins-poker-budget --template-file infra/budgets.yaml \
  --parameter-overrides AlertEmail=YOUR_EMAIL
aws cloudformation deploy --profile lawang --region us-east-1 \
  --stack-name headwins-poker-data --template-file infra/dynamodb.yaml
```

The DynamoDB table is tagged `Project=headwins-poker` and uses fixed **5 RCU /
25 WCU** in Standard provisioned mode, with no autoscaling or paid backup extras.
AWS documents an always-free allowance of 25 RCU, 25 WCU, and 25 GB; this allowance
is shared with other eligible account usage. The app stores one compressed
checkpoint rather than accumulating records. Heavy activity can throttle saves.
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
only `dynamodb:GetItem` and `dynamodb:PutItem` on the table ARN. Keep one backend
worker. The table has deletion protection and CloudFormation retention enabled;
removing the stack alone does not delete saved data.

## Checks

```sh
cd backend
./venv/bin/python -m unittest discover -s tests -v
```

```sh
cd frontend
npm run lint
npm run build
```

GitHub Actions runs the backend regression suite and frontend lint/build on pushes and pull requests. Tests cover complete hands, turn order, invalid requests, private cards, chip accounting, folded players, all-ins, ties, side pots, disconnects, sessions, the single shared game, and randomized legal play.

## Structure

- [Architecture guide](docs/architecture.md): how the components, game flow, sessions, and deployment fit together. [AGENTS.md](AGENTS.md) requires keeping it current with relevant code changes.
- `backend/game.py`: synchronous game rules and serializable player views.
- `backend/main.py`: WebSocket protocol, the game lock, sessions, bounded broadcasts, and `/health`.
- `backend/storage.py`: versioned DynamoDB checkpoints and restart recovery.
- `infra/`: CloudFormation table and monitoring budgets.
- `backend/tests/`: engine and in-process WebSocket integration tests.
- `frontend/src/App.tsx`: name entry, connection recovery, table, actions, and chat.
- `diagrams/`: original design sketches; the architecture guide describes the implemented system.

## Hosting and current limits

Build the frontend with `npm run build` and serve `frontend/dist`. Proxy `/ws` to Uvicorn with WebSocket upgrade support, or supply an explicit `VITE_WS_URL` at build time. HTTPS pages require `wss://` connections. Run **one backend worker**: live gameplay is not coordinated between processes. `/health` returns `{"status":"ok"}` unless a persistence failure has stopped the game.

This implementation is for casual play-money games. Memory-only mode loses state on restart; DynamoDB mode recovers the saved table. Everyone who opens the app joins the same game; there is no room selection, password, or account system. Long-term hand history, account authentication, distributed workers, and public-service abuse controls are separate hosting work; no real-money settlement is implemented.
