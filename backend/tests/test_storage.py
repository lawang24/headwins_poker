import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import main
from game import Table
from storage import DynamoStore, restore, snapshot


class MemoryCheckpoint:
    def __init__(self):
        self.payload = None
        self.writes = 0

    def save(self, payload, events=(), profiles=None):
        self.payload = payload
        self.writes += 1

    def identity(self, token):
        return None

    def load(self):
        return restore(self.payload) if self.payload else Table()


class PersistenceTests(unittest.TestCase):
    def test_restart_refunds_only_unfinished_hand_and_preserves_sessions(self):
        table = Table()
        a, b = table.join("Alice"), table.join("Bob")
        table.start(a.id)
        recovered = restore(snapshot(table))
        self.assertEqual([p.stack for p in recovered.players], [1000, 1000])
        self.assertEqual(recovered.pot, 0)
        self.assertFalse(recovered.running)
        self.assertTrue(all(not p.connected for p in recovered.players))
        self.assertEqual(recovered.join("Alice", a.token).id, a.id)
        self.assertEqual(recovered.join("Bob", b.token).id, b.id)
        recovered.start(a.id)
        self.assertEqual(recovered.hand_number, 2)
        recovered.act(recovered.actor, "fold")
        final = restore(snapshot(recovered))
        self.assertEqual(
            [p.stack for p in final.players], [p.stack for p in recovered.players]
        )
        self.assertEqual(final.result, recovered.result)
        self.assertEqual(sum(p.stack for p in final.players), 2000)

    def test_dynamo_roundtrip_and_optimistic_version(self):
        db = Mock()
        db.get_item.return_value = {}
        store = DynamoStore(db)
        table = store.load()
        player = table.join("Alice")
        player.stack = 765
        store.save(snapshot(table))
        item = db.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["version"], 1)
        store.save(snapshot(table))
        self.assertEqual(db.put_item.call_count, 1)
        db.get_item.return_value = {"Item": item}
        reloaded = DynamoStore(db)
        restored = reloaded.load()
        self.assertEqual(restored.join("Alice", player.token).stack, 765)
        reloaded.save(snapshot(restored))
        self.assertEqual(db.put_item.call_args.kwargs["Item"]["version"], 2)
        self.assertTrue(db.get_item.call_args.kwargs["ConsistentRead"])
        db.put_item.side_effect = RuntimeError("conditional conflict")
        with self.assertRaises(RuntimeError):
            reloaded.save(snapshot(Table()))
        self.assertEqual(reloaded.version, 2)

    def test_websocket_restart_recovers_stack_and_chat(self):
        store = MemoryCheckpoint()
        with patch.dict("os.environ", {"DYNAMODB_TABLE": ""}):
            main.server = main.GameServer(store=store)
            with TestClient(main.app) as client:
                with client.websocket_connect("/ws") as ws:
                    ws.send_json({"type": "join", "name": "Alice"})
                    session = ws.receive_json()
                    ws.receive_json()
                    ws.send_json({"type": "set_stack", "amount": 777})
                    self.assertEqual(
                        ws.receive_json()["state"]["players"][0]["stack"], 777
                    )
                    ws.send_json({"type": "chat", "text": "Persist me"})
                    ws.receive_json()
            main.server = main.GameServer(store=store)
            with TestClient(main.app) as client:
                with client.websocket_connect("/ws") as ws:
                    ws.send_json(
                        {"type": "join", "name": "Alice", "token": session["token"]}
                    )
                    self.assertEqual(ws.receive_json()["id"], session["id"])
                    state = ws.receive_json()["state"]
                    self.assertEqual(state["players"][0]["stack"], 777)
                    self.assertIn("Alice: Persist me", state["history"])
                    self.assertNotIn(session["token"], str(state))

    def test_failed_write_stops_play_without_broadcasting_uncommitted_state(self):
        store = MemoryCheckpoint()
        main.server = main.GameServer(store=store)
        with TestClient(main.app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "join", "name": "Alice"})
                ws.receive_json()
                ws.receive_json()
                saved = store.payload
                store.save = Mock(side_effect=OSError("offline"))
                ws.send_json({"type": "set_stack", "amount": 50})
                self.assertEqual(ws.receive()["code"], 1011)
                self.assertEqual(store.payload, saved)
                self.assertEqual(client.get("/health").status_code, 503)
                with client.websocket_connect("/ws") as rejected:
                    self.assertEqual(rejected.receive()["code"], 1011)
        self.assertEqual(store.save.call_count, 1)

    def test_startup_storage_error_does_not_fall_back_to_empty_game(self):
        main.server = main.GameServer(
            store=Mock(load=Mock(side_effect=OSError("offline")))
        )
        with self.assertRaises(OSError):
            with TestClient(main.app):
                pass


if __name__ == "__main__":
    unittest.main()
