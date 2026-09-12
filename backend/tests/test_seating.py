import json
import unittest

from fastapi.testclient import TestClient
import main
from game import Table, InvalidAction
from storage import restore, snapshot


class SeatingTests(unittest.TestCase):
    def setUp(self):
        self.table = Table()
        self.a = self.table.join("Alice")
        self.b = self.table.join("Bob")
        self.c = self.table.join("Charlie")

    def test_move_changes_order_preserves_chips_and_reconnects(self):
        self.table.move_seat(self.a.id, 5)
        self.assertEqual([p.id for p in self.table.players], [self.b.id, self.c.id, self.a.id])
        self.assertEqual(self.a.stack, 1000)
        self.assertEqual(self.table.join("Alice", self.a.token).seat, 5)
        recovered = restore(snapshot(self.table))
        self.assertEqual(recovered.join("Alice", self.a.token).seat, 5)
        self.table.start(self.a.id)
        self.assertEqual(self.table.dealer, self.b.id)
        self.assertEqual(self.table.actor, self.b.id)

    def test_invalid_moves_and_live_hand_removal_do_not_mutate(self):
        for seat in [True, -1, 9, "3", None, self.b.seat]:
            before = snapshot(self.table)
            with self.assertRaises(InvalidAction):
                self.table.move_seat(self.a.id, seat)
            self.assertEqual(snapshot(self.table), before)
        self.table.start(self.a.id)
        for action in [lambda: self.table.move_seat(self.a.id, 7),
                       lambda: self.table.kick(self.a.id, self.b.id)]:
            before = snapshot(self.table)
            with self.assertRaises(InvalidAction):
                action()
            self.assertEqual(snapshot(self.table), before)

    def test_kick_cashout_and_manual_rejoin(self):
        self.table.dealer = self.b.id
        self.table.kick(self.a.id, self.b.id)
        self.assertEqual(self.table.dealer, self.a.id)
        removed = [e for e in self.table.events if e["type"] == "chips_removed"]
        self.assertEqual(removed[-1]["amount"], 1000)
        self.assertEqual(removed[-1]["player_id"], self.b.id)
        self.assertEqual(self.table.join("Bob", self.b.token).id, self.b.id)
        for target in [self.a.id, "missing", None, {}]:
            with self.assertRaises(InvalidAction):
                self.table.kick(self.a.id, target)

    def test_legacy_checkpoint_assigns_distinct_seats(self):
        data = json.loads(snapshot(self.table))
        for player in data["players"]:
            player.pop("seat")
        recovered = restore(json.dumps(data))
        self.assertEqual([p.seat for p in recovered.players], [0, 1, 2])

    def test_websocket_move_and_kick(self):
        main.server = main.GameServer()
        with TestClient(main.app) as client:
            with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
                a.send_json({"type": "join", "name": "Alice"})
                sa = a.receive_json()
                a.receive_json()
                b.send_json({"type": "join", "name": "Bob"})
                sb = b.receive_json()
                b.receive_json()
                a.receive_json()
                a.send_json({"type": "move_seat", "seat": 8})
                state = a.receive_json()["state"]
                self.assertEqual(next(p["seat"] for p in state["players"] if p["id"] == sa["id"]), 8)
                self.assertEqual(b.receive_json()["state"]["players"], state["players"])
                a.send_json({"type": "kick", "player_id": sb["id"]})
                self.assertEqual(b.receive()["code"], 4002)
                self.assertEqual(len(a.receive_json()["state"]["players"]), 1)
