# Browser: presenting the game

[Architecture overview](../architecture.md)

The browser displays the server’s view of the table and collects player actions.
It owns form and connection state; it does not decide game outcomes.

## State and rendering

[App.tsx](../../frontend/src/App.tsx) owns name entry, chat, pending actions, and
connection recovery. [PokerTable.tsx](../../frontend/src/PokerTable.tsx) renders the
felt, board, bets, and nine fixed numbered seats in server seat order. Empty seats
are buttons that move the viewer between hands; occupied nameplates open a native
modal with player details and a kick confirmation for other players. Clicking
your own nameplate opens a stack editor using the existing `set_stack` command.
It starts with your current balance, supports whole-chip and cents denominations,
and permits changes only between hands while connected. Reopening the dialog or
receiving a changed balance, denomination, or hand status resets the draft. The modal
supports Escape, traps focus, and restores focus when closed. Everyone sees the
same seat positions, so moving changes both the visible position and dealing order. Desktop seats surround an oval;
portrait layouts use two side rails close to the screen edges, with a gap for the board.
The game shell in [App.css](../../frontend/src/App.css) fits the dynamic viewport.
On portrait screens, the table fills the viewport and the toolbar, chat toggle, and
betting controls overlay reserved corner/bottom areas. Table geometry stays constant
between hands and turns. Desktop keeps an oval and a separate chat column; short
landscape screens also use oval seating with a fixed bottom control lane. Nameplates have two fixed lines for name
and balance, with transient status or payout alongside the balance. Dealer markers
stay within the screen. Empty seats use numbered outlined slots.
The activity log scrolls inside its bounded panel rather than expanding the page.
[TableToolbar.tsx](../../frontend/src/TableToolbar.tsx) owns a compact Options button,
connection indicator, and Feedback in the top-right corner. Options opens a native
modal containing Settings, Invite, Leave, and expandable table instructions. The
modal supports Escape and native focus management. Branding and instructional footer
text are omitted from the playing surface; hand/street/blind metadata sits on the felt.
[Cards.tsx](../../frontend/src/Cards.tsx) embeds the 52 [clean card faces](../../frontend/src/assets/clean-cards/)
as data URLs in the JavaScript bundle, so dealing does not fetch separate card files.
Each face uses Abril Fatface rank outlines and one offset vector suit on white;
all ranks, including face cards, use the same layout. Vector outlines keep the
lettering consistent without browser font dependencies. The [asset generator](../../frontend/scripts/generate-cards.mjs)
uses shared rank outlines and suit paths to rebuild the deck. Hole cards share the same size and seven-degree fan as their backs. Portrait seats
tuck the cards behind the nameplate. A responsive picture source selects portrait
artwork with a compact corner rank and vector suit above the covered portion;
desktop seats place the larger cards beside the label. Both variants use native
61:74 artwork, so ranks and suits are never stretched. The deck README records
the font source and retained SIL Open Font License. Opponents
show card backs during play and only the server-provided result hands at showdown.
[ActionControls.tsx](../../frontend/src/ActionControls.tsx) owns the raise form and in-hand actions. Between hands it renders nothing;
the table caption indicates automatic dealing or waiting for funded players. Stack
editing stays in the viewer’s nameplate dialog. During the viewer's turn, a compact outlined row presents Call or Check,
Bet/Raise, and Fold; unavailable actions are disabled. Outside their turn the
controls render nothing and the table caption identifies the actor. Bet/Raise opens a sizing panel with numeric and slider
inputs plus minimum, half-pot, pot, and all-in presets. Presets only select a draft;
an explicit confirmation sends the raise. Cancel or Escape returns to the action
row. Pot raises include the call and then a fraction of the pot after calling;
presets are clamped to server limits, including short all-in raises. Opening bets
are labelled Bet, while the wire command remains `raise`. The draft resets when the hand, street, actor,
target, or maximum changes. Buttons disable while an action is pending or the
connection is unavailable. Below 1024px, a bottom-left toggle opens chat/activity above the table.
The action row and raise editor overlay the bottom of the table without changing
its dimensions. The raise editor is scrollable on short screens.
[main.tsx](../../frontend/src/main.tsx) mounts the app. React stores the latest complete
server snapshot alongside local form and connection state. Each new snapshot
replaces the displayed game state and clears the pending action indicator.
There is no client-side game simulation or incremental event replay.

The UI uses server-computed action limits to guide the player. The backend still
validates every request. See the [connection module](connections.md) for messages
and the [game module](game.md) for visibility rules.

## All-in runout choice

[RunoutChoice.tsx](../../frontend/src/RunoutChoice.tsx) displays a native modal over
the table or Settings whenever the server offers runouts. Eligible players see
Run once and Run twice buttons; other players see progress only. The dialog shows
who has voted and the time remaining, and disables submissions after a vote,
during a pending request, or without a connection. Escape does not dismiss an
unresolved choice; the server's deadline ensures it cannot block play indefinitely.
Closing after resolution restores native focus. The browser does not decide the
outcome from its countdown. [Runouts.css](../../frontend/src/Runouts.css) owns the
choice and result styling. [PokerTable.tsx](../../frontend/src/PokerTable.tsx) shows
two labeled boards and each run's payouts after a two-run showdown; seat payouts
show the aggregate award. Existing single-board results remain supported.

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
Options menu without dropping the connection. Any connected player can save shared
small/big blinds and cents mode. Dealing is always automatic, including the first hand;
there is no manual deal button or auto-deal toggle. The server snapshot is authoritative;
there is no browser-local settings preference. Denominations are locked during a
hand. New shared settings reset open
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
A kicked socket receives `4002`: it clears the active tab token, stops retrying, and
returns to the join screen with an explanation. The browser identity is retained
so the player may explicitly join again; kicking is removal, not a permanent ban.

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
