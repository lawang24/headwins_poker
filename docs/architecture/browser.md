# Browser: presenting the game

[Architecture overview](../architecture.md)

The browser displays the server’s view of the table and collects player actions.
It owns form and connection state; it does not decide game outcomes.

## State and rendering

[App.tsx](../../frontend/src/App.tsx) owns name entry, chat, pending actions, and
connection recovery. [PokerTable.tsx](../../frontend/src/PokerTable.tsx) renders the
felt, board, bets, and seats; it rotates the server ordering so the current player
is at the bottom while preserving clockwise order. Desktop seats surround an oval;
portrait layouts use two side rails with a gap for the board. The game shell in
[App.css](../../frontend/src/App.css) fits the dynamic viewport: header, actions,
and footer reserve their space while the table fills the remaining height. Seats
and cards adapt to the table dimensions; short landscape screens use oval seating.
The activity log scrolls inside its bounded panel rather than expanding the page.
Feedback occupies a reserved top-right header corner and cannot overlay betting controls.
[Cards.tsx](../../frontend/src/Cards.tsx) embeds the existing SVG assets as data URLs
in the JavaScript bundle, so dealing does not fetch separate card files. Opponents
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
chat/activity overlays the table on these narrower screens. The action row stays
in the layout, while the raise editor opens above it over the table so opening it
does not resize the table or create page scrolling.
[main.tsx](../../frontend/src/main.tsx) mounts the app. React stores the latest complete
server snapshot alongside local form and connection state. Each new snapshot
replaces the displayed game state and clears the pending action indicator.
There is no client-side game simulation or incremental event replay.

The UI uses server-computed action limits to guide the player. The backend still
validates every request. See the [connection module](connections.md) for messages
and the [game module](game.md) for visibility rules.

## Feedback

[Feedback.tsx](../../frontend/src/Feedback.tsx) renders a compact speech-bubble icon in the top-right header corner
on the join screen, table, and Settings page. A native modal dialog contains the
report form, traps focus, supports Escape when idle, and restores focus on close.
Drafts survive closing the dialog and failed submissions. Sending disables duplicate
clicks; confirmation appears only after the backend acknowledges persistence.
The report includes 1–2000 characters. Guests supply a name; returning browser
identities are attributed to their server-side player profile. A separate short-lived
WebSocket to `/feedback` uses the same backend host as `VITE_WS_URL` (replacing
its trailing `/ws`) and does not join a seat or interrupt the game connection.

## Lobby settings

[Settings.tsx](../../frontend/src/Settings.tsx) is a dedicated page opened from the
header without dropping the connection. Any connected player can deal a hand when two players have chips, and save shared
small/big blinds, cents mode, and auto-deal. The server snapshot is authoritative;
there is no browser-local settings preference. Denominations are locked during a
hand; auto-deal can be switched off at any time. New shared settings reset open
drafts, and leaving the page discards unsaved changes.

[amounts.ts](../../frontend/src/amounts.ts) formats amounts and converts numeric
inputs to integer wire units. With cents enabled, 100 wire units equal 1.00;
otherwise they equal 100 whole chips. Switching modes preserves integer balances
and blinds, changing their denomination for everyone. Bets, stacks, payouts, and
blind labels use the shared mode. Historical activity text retains its original
integer-unit amounts. Inputs accept increments of 0.01 in cents mode and 1 otherwise.

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

During development, Vite proxies `/ws`, `/feedback`, and `/health` to the backend on port 8000.
The frontend normally derives the WebSocket address from the page's host and
protocol; `VITE_WS_URL` can override it.

For production routing and serving, see [operations](operations.md#serving-the-app).
