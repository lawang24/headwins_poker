"""Server-authoritative, integer-chip no-limit Hold'em for independent tables."""

from dataclasses import dataclass, field
from uuid import uuid4
from deck_of_cards import DeckOfCards
from phevaluator.evaluator import evaluate_cards


class InvalidAction(ValueError):
    pass


def chips(value):
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise InvalidAction("Use a whole-chip amount between 0 and 1,000,000.")
    return value


@dataclass
class Player:
    id: str
    name: str
    token: str
    stack: int = 1000
    connected: bool = True
    hand: list = field(default_factory=list)
    in_hand: bool = False
    folded: bool = False
    committed: int = 0
    contribution: int = 0
    acted_at: int | None = None


class Table:
    def __init__(self):
        self.players = []
        self.dealer = None
        self.actor = None
        self.street = "waiting"
        self.board = []
        self.pot = 0
        self.target = 0
        self.min_raise = 10
        self.small_blind = 5
        self.big_blind = 10
        self.pending = set()
        self.result = None
        self.history = []
        self.hand_number = 0
        self.deck = DeckOfCards()

    @property
    def running(self):
        return self.street in {"preflop", "flop", "turn", "river"}

    @property
    def host(self):
        return next((p.id for p in self.players if p.connected), None)

    def player(self, player_id):
        return next(p for p in self.players if p.id == player_id)

    def join(self, name, token=None):
        if token:
            existing = next((p for p in self.players if p.token == token), None)
            if existing:
                existing.connected = True
                return existing
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 24:
            raise InvalidAction("Choose a name of 1–24 characters.")
        # Retain seats during hands so reconnects cannot change turn order.
        if not self.running:
            self.players = [p for p in self.players if p.connected]
        if len(self.players) >= 9:
            raise InvalidAction("This table is full (9 seats).")
        base = name.strip()
        name = base
        suffix = 2
        while any(p.name == name for p in self.players):
            name = f"{base[:20]} {suffix}"
            suffix += 1
        p = Player(uuid4().hex, name, uuid4().hex)
        self.players.append(p)
        return p

    def clockwise(self, after, candidates):
        ids = [p.id for p in self.players]
        start = ids.index(after) if after in ids else -1
        return next(
            (
                ids[(start + i) % len(ids)]
                for i in range(1, len(ids) + 1)
                if ids[(start + i) % len(ids)] in candidates
            ),
            None,
        )

    def log(self, message):
        self.history = (self.history + [message])[-100:]

    def pay(self, p, amount):
        amount = min(amount, p.stack)
        p.stack -= amount
        p.committed += amount
        p.contribution += amount
        self.pot += amount

    def start(self, player_id):
        if player_id != self.host:
            raise InvalidAction("Only the table host can deal a hand.")
        if self.running:
            raise InvalidAction("Finish the current hand before dealing again.")
        eligible = {p.id for p in self.players if p.connected and p.stack > 0}
        if len(eligible) < 2:
            raise InvalidAction("At least two connected players with chips are needed.")
        self.dealer = self.clockwise(self.dealer, eligible)
        self.deck = DeckOfCards()
        self.deck.shuffle()
        self.board, self.pot, self.result = [], 0, None
        self.target, self.min_raise = self.big_blind, self.big_blind
        self.hand_number += 1
        self.street = "preflop"
        for p in self.players:
            p.in_hand = p.id in eligible
            p.folded = False
            p.committed = p.contribution = 0
            p.acted_at = None
            p.hand = [self.deck.draw(), self.deck.draw()] if p.in_hand else []
        sb = (
            self.dealer if len(eligible) == 2 else self.clockwise(self.dealer, eligible)
        )
        bb = self.clockwise(sb, eligible)
        self.pay(self.player(sb), self.small_blind)
        self.pay(self.player(bb), self.big_blind)
        self.pending = {p.id for p in self.players if p.in_hand and p.stack > 0}
        self.log(
            f"Hand {self.hand_number}: {self.player(self.dealer).name} is the dealer."
        )
        self.advance(bb)

    def live(self):
        return [p for p in self.players if p.in_hand and not p.folded]

    def can_raise(self, p):
        return p.acted_at is None or self.target - p.acted_at >= self.min_raise

    def act(self, player_id, action, amount=None):
        if not self.running or player_id != self.actor:
            raise InvalidAction("Wait for your turn.")
        p = self.player(player_id)
        if action == "fold":
            p.folded = True
            self.log(f"{p.name} folds.")
        elif action in {"check_call", "raise"}:
            total = (
                min(self.target, p.committed + p.stack)
                if action == "check_call"
                else chips(amount)
            )
            if total < p.committed or total > p.committed + p.stack:
                raise InvalidAction(
                    "That bet exceeds your available chips or reduces your bet."
                )
            if total < self.target and total != p.committed + p.stack:
                raise InvalidAction(
                    "Call the current bet, or go all-in with your remaining chips."
                )
            if action == "raise" and total <= self.target:
                raise InvalidAction("A raise must exceed the current bet.")
            if total > self.target:
                if not self.can_raise(p):
                    raise InvalidAction(
                        "A short all-in has not reopened raising for you."
                    )
                if not any(q.id != p.id and q.stack > 0 for q in self.live()):
                    raise InvalidAction(
                        "There is no opponent with chips to call a raise."
                    )
                increase = total - self.target
                if increase < self.min_raise and total != p.committed + p.stack:
                    raise InvalidAction(
                        f"Raise to at least {self.target + self.min_raise}, or go all-in."
                    )
                if increase >= self.min_raise:
                    self.min_raise = increase
                self.target = total
                self.pending.update(
                    q.id
                    for q in self.live()
                    if q.id != p.id and q.stack > 0 and q.committed < total
                )
            paid = total - p.committed
            self.pay(p, paid)
            p.acted_at = self.target
            self.log(
                f"{p.name} {'checks' if paid == 0 else f'puts in {paid} (total {total})'}."
            )
        else:
            raise InvalidAction("Unknown poker action.")
        self.pending.discard(p.id)
        self.advance(p.id)

    def advance(self, after):
        while self.running:
            live = self.live()
            if len(live) <= 1:
                self.finish()
                return
            able = [p for p in live if p.stack > 0]
            self.pending.intersection_update(p.id for p in able)
            # A lone player can only act when facing an outstanding bet.
            if len(able) <= 1:
                if able:
                    self.target = max(
                        (p.committed for p in live if p.id != able[0].id), default=0
                    )
                self.pending = {p.id for p in able if p.committed < self.target}
            if self.pending:
                self.actor = self.clockwise(after, self.pending)
                return
            if self.street == "river":
                self.finish()
                return
            self.street = {"preflop": "flop", "flop": "turn", "turn": "river"}[
                self.street
            ]
            self.deck.draw()  # burn
            self.board.extend(
                self.deck.draw() for _ in range(3 if self.street == "flop" else 1)
            )
            self.target, self.min_raise = 0, self.big_blind
            for p in self.players:
                p.committed = 0
                p.acted_at = None
            self.pending = {p.id for p in able} if len(able) >= 2 else set()
            after = self.dealer

    def finish(self):
        live = self.live()
        payouts = {p.id: 0 for p in self.players}
        pots = []
        if len(live) == 1:
            payouts[live[0].id] = self.pot
            pots.append({"amount": self.pot, "winners": [live[0].id]})
        elif live:
            previous = 0
            ranks = {p.id: evaluate_cards(*(self.board + p.hand)) for p in live}
            for level in sorted(
                {p.contribution for p in self.players if p.contribution > 0}
            ):
                contributors = [p for p in self.players if p.contribution >= level]
                amount = (level - previous) * len(contributors)
                previous = level
                eligible = [p for p in live if p.contribution >= level]
                # Uncalled chips are returned, even if their owner disconnected.
                if len(contributors) == 1:
                    winners = [contributors[0].id]
                elif not eligible:
                    # No live contender for this layer: return each excess contribution.
                    for p in contributors:
                        payouts[p.id] += amount // len(contributors)
                    continue
                else:
                    best = min(ranks[p.id] for p in eligible)
                    winners = [p.id for p in eligible if ranks[p.id] == best]
                ordered = []
                after = self.dealer
                remaining = set(winners)
                while remaining:
                    after = self.clockwise(after, remaining)
                    ordered.append(after)
                    remaining.remove(after)
                share, odd = divmod(amount, len(ordered))
                for i, pid in enumerate(ordered):
                    payouts[pid] += share + (i < odd)
                pots.append({"amount": amount, "winners": ordered})
        else:
            payouts = {p.id: p.contribution for p in self.players}
        for p in self.players:
            p.stack += payouts[p.id]
        self.result = {
            "payouts": payouts,
            "pots": pots,
            "hands": {p.id: p.hand for p in live} if len(live) > 1 else {},
        }
        self.log(
            "Hand complete. "
            + ", ".join(
                f"{p.name} receives {payouts[p.id]}"
                for p in self.players
                if payouts[p.id]
            )
        )
        self.pot = 0
        self.actor = None
        self.pending = set()
        self.street = "complete"

    def disconnect(self, player_id):
        p = self.player(player_id)
        p.connected = False
        if self.running and p.in_hand and not p.folded and p.stack > 0:
            p.folded = True
            self.pending.discard(p.id)
            self.log(f"{p.name} disconnected and folded.")
            # Preserve the current actor unless the departing seat owned the turn.
            if self.actor == p.id or len(self.live()) <= 1:
                self.advance(p.id)
            else:
                ids = [q.id for q in self.players]
                self.advance(ids[(ids.index(self.actor) - 1) % len(ids)])

    def set_stack(self, player_id, amount):
        if self.running:
            raise InvalidAction("Stacks can only be changed between hands.")
        self.player(player_id).stack = chips(amount)

    def state(self, viewer):
        p = self.player(viewer)
        max_total = p.committed + p.stack
        raise_allowed = (
            self.actor == viewer
            and self.can_raise(p)
            and max_total > self.target
            and any(q.id != viewer and q.stack > 0 for q in self.live())
        )
        return {
            "players": [
                {
                    "id": q.id,
                    "name": q.name,
                    "stack": q.stack,
                    "connected": q.connected,
                    "in_hand": q.in_hand,
                    "folded": q.folded,
                    "committed": q.committed,
                    "all_in": q.in_hand and not q.folded and q.stack == 0,
                }
                for q in self.players
            ],
            "you": viewer,
            "host": self.host,
            "dealer": self.dealer,
            "actor": self.actor,
            "street": self.street,
            "running": self.running,
            "board": self.board,
            "hand": p.hand,
            "pot": self.pot,
            "target": self.target,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "min_raise_to": self.target + self.min_raise,
            "max_raise_to": max_total,
            "can_raise": raise_allowed,
            "call_amount": min(p.stack, max(0, self.target - p.committed)),
            "result": self.result,
            "history": self.history,
            "hand_number": self.hand_number,
        }
