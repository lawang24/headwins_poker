# Persistence: recovery and permanent history

[Architecture overview](../architecture.md)

The backend saves a recovery checkpoint and an append-only archive in one
DynamoDB transaction before acknowledging joins or publishing state. Configure
both `DYNAMODB_TABLE` and `DYNAMODB_HISTORY_TABLE`; if the checkpoint table is set
without a history table, startup fails rather than silently dropping history.
With `DYNAMODB_TABLE` empty, play remains memory-only and history is not retained.

[storage.py](../../backend/storage.py) owns AWS access and recovery.
[archive.py](../../backend/archive.py) maps engine events to archive records and
provides paginated reads. [GameServer](../../backend/main.py) owns the save boundary;
boto3 calls run off the event loop while game changes remain ordered by one lock.

## Access patterns and schema

The existing checkpoint table keeps its string partition key `pk=GAME#GLOBAL`,
with increasing `version` and a compressed binary JSON `payload`. Schema 2 adds
session/hand IDs, starting-hand data, and the event sequence to the existing
players, chips, board, result, blinds, and recent display log. Shared cents and
auto-deal settings are also saved, defaulting to false for older checkpoints.
The pending auto-deal timer is transient and is recreated only when eligible
players reconnect to a completed hand. The checkpoint remains bounded.

The history table has string `pk` and `sk` keys. It has no secondary indexes,
streams, or TTL. Events and summaries retain data indefinitely; profiles can
update their display names but never change their associated player ID.

| Read/write need | Partition key | Sort key | Contents |
| --- | --- | --- | --- |
| Read private feedback chronologically | `FEEDBACK` | `<UTC-timestamp>#<report-id>` | Message, server timestamp, reporter name/type and nullable player ID. |
| Resolve returning browser identity | `IDENTITY#<sha256(token)>` | `PROFILE` | Stable player ID and display name; no raw token. |
| Read player profile | `PLAYER#<id>` | `PROFILE` | Stable player ID and display name. |
| Discover session boundaries | `SESSIONS` | `<timestamp>#<sequence>` | Start/end or legacy-import event. |
| Read ordered session history | `SESSION#<id>` | `EVENT#<20-digit-sequence>` | Compressed event JSON. |
| Read ordered hand history | `HAND#<id>` | `EVENT#<20-digit-sequence>` | The same event, copied for direct hand queries. |
| Read finished/cancelled hand | `HAND#<id>` | `SUMMARY` | Start data, result/refund, board, ending players, net results. |
| Aggregate player profit/loss | `PLAYER#<id>` | `RESULT#<timestamp>#<hand-id>` | Net integer chips, hand/session IDs, name, status, ending stack. |
| Audit player chip transfers | `PLAYER#<id>` | `MOVEMENT#<timestamp>#<sequence>` | Chip additions/removals with reason and session ID. |
| Read between-session changes | `SYSTEM` | `EVENT#<20-digit-sequence>` | Events such as pruning old retained seats outside an open session. |

Startup performs one strongly consistent checkpoint read. An unretained returning
identity requires one strongly consistent profile read. Saves use conditional
`TransactWriteItems` across both tables: the checkpoint version must match, new
archive keys must not exist, and profile IDs cannot be reassigned. A request token
makes SDK retries of the same transaction idempotent. Identical checkpoints with
no pending events or profiles skip writes. There are no scans or reads for each
player refresh. Private exports use paginated, strongly consistent `Query` calls.

A normal command affects a bounded number of records (at most nine players),
independent of total history. Payloads have a 350,000-byte compressed guard and
transactions a 100-item guard. DynamoDB also enforces its aggregate transaction
size limit; a rejected save stops play. Session and player partitions grow with
use; this design targets one casual shared table, not distributed high-volume play.

## Feedback storage

[feedback.py](../../backend/feedback.py) validates reports and resolves existing
browser identities without joining a seat. It generates the report ID and UTC
timestamp on the server, then calls `DynamoStore.save_feedback` to write one record
to the history table. Guest names are self-reported and have no player ID; supplied
browser identities must resolve to a retained seat or durable profile. Submitted
names cannot override an identified player's name. Records contain no reconnect
credentials and never enter game state, chat, checkpoints, or broadcasts.

Feedback writes are independent of game transactions and remain available if play
has stopped after a checkpoint failure, provided the history store works. Missing
storage, lookup failures, and failed/uncertain writes return errors without claiming
success or stopping play. An uncertain write may have committed; a manual resubmission
can create a duplicate. Memory-only mode does not accept feedback. Records have no
TTL and can be read privately with `export_history.py --feedback` using the existing
paginated export and owner-only output file.

## Sessions, identity, and accounting

A session starts with the first join and ends when everyone disconnects or the
backend restarts. Retained seats can reconnect with their existing stacks; new
seats start at 1,000. Identity profiles outlive seats. The browser retains its
credential across visits, but there is no cross-device account or identity recovery.

Seat entry, stack adjustments, seat removal, and session closure create distinct
chip-transfer records. Hand profit is payout minus contribution, including
returned uncalled chips. Therefore a rebuy is not a win, a cash-out is not a loss,
and cancelled hands have zero net. Per-hand results can be summed by player and
session without replaying every action. No balances are inferred from names.

## Restart and migration

Startup accepts schema 1 or 2 checkpoints. Schema 1 imports retained player IDs
and creates a `history_started` baseline containing the available players, recent
log, board, and result. Prior actions and sessions cannot be recovered from the
old checkpoint; no historical profit is invented. Once saved as schema 2, older
backend versions cannot read the checkpoint, so deploy the new backend as a unit.

Retained seats restore as disconnected. If a saved hand was unfinished, recovery
refunds contributions, records `hand_cancelled` with zero net, and clears live
cards/bets. The previous session closes with recorded cash-outs. Completed payouts
are never refunded or recorded twice. The recovery changes and archive records
commit together before accepting connections; the next join opens a new session.
Session end timestamps after a crash indicate when recovery detected closure,
not an inferred crash time. Recovery still cancels rather than resumes a hand.

## Privacy and analysis

The archive holds every accepted game action, chat entry, actual hole cards,
board/burn cards, deck order, results, and lifecycle events after activation.
Rejected requests and transport frames are not game history. Raw reconnect tokens
remain only in private checkpoints and the joining player's session response;
archive events and exports omit them. Compression is not encryption. Storage uses
DynamoDB's default encryption at rest and HTTPS in transit.

[export_history.py](../../backend/export_history.py) writes private JSON files for
session discovery, session/hand history, system events, or player results. Player
exports include lifetime and per-session net chips plus underlying records. Files
are created exclusively with owner-only permissions. The CLI requires authorized
AWS access; no public history endpoint exposes live cards. See the
[README](../../README.md#exporting-history) for commands.

These records support future equity analysis using the information available at
any street. An equity calculator, player-facing history/report UI, account login,
and cross-device identity linking are future work. Export queries paginate, but
the CLI assembles the selected partition in memory; large analytical workloads
will need a streaming export or a dedicated analytics pipeline.

## Failure handling

A failed or uncertain transaction, including a version conflict, stops further
game changes: sockets close with `1011` and `/health` returns 503. Pending events
are not discarded on failure. Restart reloads the authoritative checkpoint; an
uncertain transaction either committed both checkpoint and archive or neither.
Startup failures abort rather than silently creating an empty game. Version
checks prevent stale overwrites but do not coordinate multiple workers.

Identity lookup failures close the joining socket for retry without changing the
table or creating a replacement identity. Other players can continue playing.

## Verification

[Persistence tests](../../backend/tests/test_storage.py) cover recovery and save
failures. [History tests](../../backend/tests/test_history.py) cover card/runout
reconstruction, identity after pruning/restart, chip accounting, migration,
archive privacy, pagination, SDK transaction serialization, and uncertain commits.
They run without AWS access. See [operations](operations.md#storage-infrastructure)
for infrastructure and [README](../../README.md#checks) for verification commands.
