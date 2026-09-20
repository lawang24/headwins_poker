# Game: rules and player views

[Architecture overview](../architecture.md)

The game engine owns the table and decides what each action means. It is
synchronous and independent of WebSockets, so rules can be tested without a
running server. Its implementation is [game.py](../../backend/game.py).

## Hand lifecycle

The table begins in `waiting`, moves through `preflop`, `flop`, `turn`, and `river`,
and ends in `complete`. A hand can finish early when only one player remains.
When all calls are settled and at most one remaining player has chips, betting
is closed. Before the river, the engine pauses on the current street with no actor
and offers every non-folded contender a choice of one or two runouts. This includes
a covering player with chips left. Two runs require unanimous agreement; any
one-run vote, a disconnected contender, or the 20-second deadline resolves to one.
Folded players and new arrivals observe but cannot vote. A river all-in or an
uncontested hand settles immediately without a vote.

Each run copies the existing board and draws its remaining streets, including
burn cards, sequentially from the same deck without reshuffling or replacement.
Every contested main/side-pot layer is divided between runs before evaluating
winners; an odd chip goes to the first run. Ties within each run award odd chips
clockwise left of the dealer. Uncalled contributions are returned once, outside
runout payouts. The result includes each run's board, pots and payouts, alongside
aggregate payouts; the legacy `board` is the first run. If insufficient cards
remain for two runs, the engine falls back to one.
The result stays visible for five seconds before the next automatic deal when at
least two connected players have chips. The first hand uses the same delay;
otherwise the table waits until enough funded players connect.

## Rules and shared state

The engine owns blinds, dealer rotation, turn order, minimum raises, all-in
eligibility, main/side pots, ties, and uncalled-chip returns. Chips are integers;
players start with 1,000 and blinds are 5/10. Players can set their own stack
between hands. Players have stable numbered seats; the engine keeps its player
list sorted by seat for clockwise dealing and action order. Moves to empty seats
and removal of other players are allowed only between hands. Removal records a
cash-out and preserves the next dealer when removing the current dealer.
Seat numbers are checkpointed; older checkpoints derive them from list order.
Moves emit `seat_changed` events, and kicks attribute `seat_removed` to the requester.
Any connected player can change the shared lobby settings:
positive integer-unit blinds (SB ≤ BB ≤ 1,000,000) and cents mode.
Blinds and cents can change only between hands. Automatic dealing is always enabled.
Cents mode denominates each integer unit as 0.01 instead of 1 for everyone;
switching modes preserves underlying chip balances. The default denomination is whole chips. Settings are checkpointed with backward-compatible defaults and
emit a `settings_changed` archive event. Chat and game activity share a rolling display log of 100 entries.
The engine also emits structured, ordered private events for joins, seat removal,
chip movements, blinds, actions (including forced folds), runout offers/votes/decisions,
boards (indexed by runout during an all-in), chat, and results.
Each event has a schema version, UTC timestamp, sequence, session ID, and hand ID
when applicable. Hand starts capture seat order, starting stacks, all hole cards,
and the shuffled deck in draw order. Completion captures contributions, payouts,
ending stacks, and per-player net (`payout - contribution`).

Pending events and identity registrations live on `Table` only until the connection
layer saves them. They are cleared after a successful save (or discarded in
memory-only mode). `hand_start`, hand/session IDs, and the sequence are checkpointed
for recovery; the entire accumulated archive is never loaded into the engine.

[DeckOfCards](../../backend/deck_of_cards.py) creates, shuffles, and draws from a
52-card deck. The engine uses `phevaluator` to rank hands at showdown; the
package is declared in [requirements.txt](../../backend/requirements.txt).

## Player privacy

`Table.state(viewer)` is the privacy boundary. It includes public seat information,
the board and betting state, the viewer's hole cards, and server-computed action
limits. Opponents' hole cards are absent until a contested showdown exposes the
remaining hands in the result. Session tokens are sent in the joining player's
session response, not in table snapshots.

The server sends these views through the [connection module](connections.md).
[Recovery checkpoints and archives](persistence.md) use separate private representations.
Archive events strip bearer tokens, but include hidden cards and deck order;
only authorized offline analysis can read them. They never appear in `state`.
Identity lookup records use a SHA-256 digest of the random token.

## Verification

[Engine tests](../../backend/tests/test_game.py) cover turn order, betting rules,
payouts, privacy, disconnects, and chip conservation, including randomized legal
hands. [Settings tests](../../backend/tests/test_settings.py) cover shared-setting
validation, checkpoint compatibility, delayed deals, cancellation, and disconnects.
[Runout tests](../../backend/tests/test_runouts.py) cover consent, deadlines,
card uniqueness, shared board prefixes, side pots, odd chips, reconnects and recovery.
See the [README](../../README.md#checks) for test commands.
