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
between hands. Chat and game activity share a rolling history of 100 entries.

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
[Recovery checkpoints](persistence.md) use a separate private representation.

## Verification

[Engine tests](../../backend/tests/test_game.py) cover turn order, betting rules,
payouts, privacy, disconnects, and chip conservation, including randomized legal
hands. See the [README](../../README.md#checks) for test commands.
