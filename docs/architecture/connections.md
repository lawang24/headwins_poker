# Connections: coordinating players

[Architecture overview](../architecture.md)

The WebSocket server connects player sessions to the shared game. It validates
messages and orders changes so every player sees a consistent, private view.
The implementation lives in [main.py](../../backend/main.py).

## Command flow

1. A player enters a display name. The browser opens `/ws` and sends a `join`
   message with the name and any saved session token.
2. The backend restores a retained seat matching that token, or looks up its
   permanent identity before creating a new seat. Unknown tokens create a new
   identity; display names never merge identities. It returns a `session` message
   containing the stable player ID and token, then sends
   each connected player a `state` message with their own complete table view.
3. The first connected seat is the host. The host can deal when at least two
   connected players have chips. New players joining during a hand wait for the
   next one.
4. The browser sends commands such as `fold`, `check_call`, or `raise`. A raise's
   `amount` is the total commitment for the current betting street. `start`,
   `set_stack`, and `chat` cover dealing, between-hand stack changes, and messages.
5. FastAPI handles game commands under one `asyncio.Lock`. The engine checks the
   action, changes the table, and advances play as needed. Invalid requests
   receive an `error` message; frontend button restrictions are only a convenience,
   and the backend enforces the rules.
6. With persistence enabled, the server atomically saves changed state and its
   pending events, identity records, and result summaries before acknowledging
   joins or broadcasting fresh snapshots, generated separately for each player.
   React replaces its displayed state with the snapshot and clears the pending
   action indicator. There is no client-side simulation or incremental event replay.

## Message reference

All messages are JSON text over `/ws`. Clients join before sending game commands.

| Direction | Type | Payload and meaning |
| --- | --- | --- |
| Client → server | `join` | `name` and optional saved `token`; create or reclaim a seat. |
| Client → server | `start` | Host requests the next hand. |
| Client → server | `fold`, `check_call` | Act on the current turn. |
| Client → server | `raise` | `amount` is the total commitment for this street. |
| Client → server | `set_stack` | `amount` sets the player’s stack between hands. |
| Client → server | `chat` | `text` contains 1–300 characters after trimming. |
| Server → client | `session` | `id` is the stable player ID; `token` is its browser credential. |
| Server → client | `state` | `state` contains that player’s complete table view. |
| Server → client | `error` | `message` explains an invalid request. |

## Seat lifecycle

A disconnected player with chips folds an active hand. An all-in player remains
eligible for the pot. Reconnection does not undo a fold. Seats are retained during
hands to preserve order; a new join between hands prunes disconnected seats.
Pruning records a cash-out. A retained seat keeps its chips on reconnect; a pruned
seat starts with 1,000 again under the same player ID, recorded as a new chip entry.
The host role follows the first connected seat.

A table session opens on the first join and closes when everyone disconnects or
on restart. Reconnecting within an open session does not add another buy-in.
Closing records cash-outs for remaining session members; reconnecting retained
seats into the next session records their opening stacks. This bookkeeping does
not change stacks or count chip transfers as poker profit.

The [browser](browser.md#reconnecting-to-a-seat) manages reconnect attempts and
handles replacement connections. Retained seats can also survive a backend
restart when [persistence](persistence.md) is enabled.

## Ordering and failed connections

Broadcasts send concurrently to connected sockets while holding the game lock,
with a two-second timeout per send. Failed sockets are removed, the engine applies
disconnect behavior, and surviving clients receive the repaired state. This
keeps mutations and the snapshots describing them ordered.

An identity lookup failure closes only the joining connection with `1011` so it
can retry, without inventing a new identity. Persistence write failures stop further play; see [failure handling](persistence.md#failure-handling).
