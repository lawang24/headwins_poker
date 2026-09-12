# Persistence: recovering the table

[Architecture overview](../architecture.md)

Persistence lets the shared table survive a backend restart. It saves recovery
checkpoints, not a replayable record of every hand. Without `DYNAMODB_TABLE`, the
app runs in memory and loses state on restart.

The implementation lives in [storage.py](../../backend/storage.py).
[GameServer](../../backend/main.py) saves changed state before acknowledging joins
or broadcasting new snapshots. boto3 calls run off the event loop.

## Restart behavior

With DynamoDB enabled, startup restores retained seats as disconnected. If the
last saved hand was unfinished, recovery cancels it and refunds each player's
contribution, preserving chip totals. Completed payouts are never refunded. Players
reclaim seats with their existing tab tokens; normal between-hand pruning still
applies. This is recovery of a casual game, not replay of an interrupted hand.

## Checkpoint format and access

The access patterns are one strongly consistent `GetItem` on startup and one
conditional `PutItem` per changed checkpoint. The partition key is
`pk=GAME#GLOBAL`; there are no scans, secondary indexes, streams, or database
reads per browser refresh. A schema-versioned JSON document is compressed into
the binary `payload` attribute, alongside an increasing `version`. The single
item bounds stored history and makes each save atomic. Identical checkpoints
skip writes. The saved format is separate from `Table.state(viewer)` and never
goes to browsers; compression is not encryption. DynamoDB's default AWS-owned key
encrypts storage at rest, and boto3 uses HTTPS and the normal AWS identity chain.

## Failure handling

A failed or uncertain write, including a version conflict, stops the process
from accepting further game changes: sockets close with code `1011`, and
`/health` returns HTTP 503. Restart after resolving the storage problem to reload
the authoritative checkpoint. Startup read failures abort startup rather than
silently creating an empty game. Version checks prevent stale overwrites but do
not provide distributed game coordination; only one worker is supported.

## Verification

[Persistence tests](../../backend/tests/test_storage.py) verify restart refunds,
completed payouts, session/stack/chat recovery, conditional versions, and failure
behavior without AWS access. Infrastructure and capacity are described in
[operations](operations.md#storage-infrastructure).
