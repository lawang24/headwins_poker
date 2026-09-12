# Browser: presenting the game

[Architecture overview](../architecture.md)

The browser displays the server’s view of the table and collects player actions.
It owns form and connection state; it does not decide game outcomes.

## State and rendering

[App.tsx](../../frontend/src/App.tsx) owns name entry, chat, pending actions, and
connection recovery. [PokerTable.tsx](../../frontend/src/PokerTable.tsx) renders the
felt, board, bets, and seats; it rotates the server ordering so the current player
is at the bottom while preserving clockwise order. Desktop seats surround an oval;
portrait layouts use two side rails with a gap for the board.
[Cards.tsx](../../frontend/src/Cards.tsx) reuses the existing SVG assets. Opponents
show card backs during play and only the server-provided result hands at showdown.
[ActionControls.tsx](../../frontend/src/ActionControls.tsx) owns the raise and stack
forms. Numeric and slider inputs share a draft, bounded by the server limits,
including short all-in raises. The draft resets when the hand, street, actor,
target, or maximum changes. Buttons disable while an action is pending or the
connection is unavailable. Below 1024px, a header toggle opens chat/activity;
phone controls remain in document flow so they cannot cover the bottom seat.
[main.tsx](../../frontend/src/main.tsx) mounts the app. React stores the latest complete
server snapshot alongside local form and connection state. Each new snapshot
replaces the displayed game state and clears the pending action indicator.
There is no client-side game simulation or incremental event replay.

The UI uses server-computed action limits to guide the player. The backend still
validates every request. See the [connection module](connections.md) for messages
and the [game module](game.md) for visibility rules.

## Reconnecting to a seat

The browser saves its name and token in tab-scoped `sessionStorage`. After a
connection closes, it retries with exponential backoff capped at ten seconds and
uses the token to reclaim its seat. A second connection using the same token
replaces the first; the old socket receives close code `4001` and stops retrying.
Tokens identify seats; the app has no account or password authentication.

Seat retention and the effect of disconnecting during a hand are described in
[connections and sessions](connections.md#seat-lifecycle).

## Build and server address

Vite serves the development UI and builds static production assets; TypeScript
and ESLint check the frontend. See [vite.config.ts](../../frontend/vite.config.ts)
and [package.json](../../frontend/package.json).

During development, Vite proxies `/ws` and `/health` to the backend on port 8000.
The frontend normally derives the WebSocket address from the page's host and
protocol; `VITE_WS_URL` can override it.

For production routing and serving, see [operations](operations.md#serving-the-app).
