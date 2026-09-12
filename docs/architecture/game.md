# Game: rules and player views

[Architecture overview](../architecture.md)

The game engine owns the table and decides what each action means. It is
synchronous and independent of WebSockets, so rules can be tested without a
running server. Its implementation is [game.py](../../backend/game.py).

## Hand lifecycle

The table begins in `waiting`, moves through `preflop`, `flop`, `turn`, and `river`,
and ends in `complete`. A hand can finish early when only one player remains.
When no further betting is possible, the engine automatically runs out the board.
The result stays visible until the host deals again.

## Rules and shared state

The engine owns blinds, dealer rotation, turn order, minimum raises, all-in
eligibility, main/side pots, ties, and uncalled-chip returns. Chips are integers;
players start with 1,000 and blinds are 5/10. Players can set their own stack
between hands. Chat and game activity share a rolling display log of 100 entries.
The engine also emits structured, ordered private events for joins, seat removal,
chip movements, blinds, actions (including forced folds), boards, chat, and results.
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
hands. See the [README](../../README.md#checks) for test commands.
