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
forms. During the viewer's turn, a compact outlined row presents Call, Bet/Raise,
Check, and Fold; unavailable actions are disabled. Outside their turn only the
waiting status is shown. Bet/Raise opens a sizing panel with numeric and slider
inputs plus minimum, half-pot, pot, and all-in presets. Presets only select a draft;
an explicit confirmation sends the raise. Cancel or Escape returns to the action
row. Pot raises include the call and then a fraction of the pot after calling;
presets are clamped to server limits, including short all-in raises. Opening bets
are labelled Bet, while the wire command remains `raise`. The draft resets when the hand, street, actor,
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

The browser keeps its name and bearer token in `localStorage` across visits.
Tab-scoped `sessionStorage` keeps the active tab's identity and whether to reconnect
on reload; old tab tokens take precedence and migrate to local storage after a
successful join. Leaving clears the active tab token but retains the browser identity.
A newly opened tab shows the join form and reuses the browser identity on joining.
Use separate browser profiles for separate people; names do not identify players.
Clearing browser storage loses access to that identity, and cross-device login and
account recovery are not implemented.

After a connection closes, the browser retries with exponential backoff capped at
ten seconds. The token reclaims a retained seat or creates a new seat with the
same permanent player ID after pruning. A second connection using the same token
replaces the first; the old socket receives close code `4001` and stops retrying.

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
