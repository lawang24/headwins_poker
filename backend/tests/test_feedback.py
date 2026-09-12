import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import main
from storage import DynamoStore


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.history = Mock()
        self.store = DynamoStore(Mock(), self.history)
        self.server = main.GameServer(store=self.store)
        self.patch = patch.object(main, "server", self.server)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.client = TestClient(main.app)

    def submit(self, data):
        with self.client.websocket_connect("/feedback") as ws:
            ws.send_json(data)
            return ws.receive_json()

    def record(self):
        return self.history.put_item.call_args.kwargs["Item"]

    def test_guest_is_persisted_with_server_time_and_no_seat(self):
        reply = self.submit({"message": "  More themes please  ", "name": " Guest ", "created_at": "fake", "player_id": "fake"})
        self.assertEqual(reply["type"], "feedback_saved")
        record = self.record()
        self.assertEqual(record["message"], "More themes please")
        self.assertEqual(record["reporter_name"], "Guest")
        self.assertEqual(record["reporter_type"], "guest")
        self.assertIsNone(record["player_id"])
        self.assertEqual(record["pk"], "FEEDBACK")
        self.assertTrue(record["sk"].endswith(reply["id"]))
        self.assertIsNotNone(datetime.fromisoformat(record["created_at"]).tzinfo)
        self.assertEqual(self.server.table.players, [])

    def test_retained_player_identity_is_authoritative_and_private(self):
        player = self.server.table.join("Alice")
        before = list(self.server.table.events)
        reply = self.submit({"message": "Bug", "name": "Impersonation", "token": player.token})
        self.assertEqual(reply["type"], "feedback_saved")
        self.assertEqual(self.record()["player_id"], player.id)
        self.assertEqual(self.record()["reporter_name"], "Alice")
        self.assertNotIn(player.token, json.dumps(self.record()))
        self.assertEqual(before, self.server.table.events)

    def test_profile_resolves_after_seat_pruning(self):
        self.history.get_item.return_value = {"Item": {"player_id": "old-id", "name": "Alice"}}
        self.assertEqual(self.submit({"message": "Bug", "token": "existing"})["type"], "feedback_saved")
        self.assertEqual(self.record()["player_id"], "old-id")
        self.assertTrue(self.history.get_item.call_args.kwargs["ConsistentRead"])

    def test_invalid_input_is_not_saved(self):
        self.history.get_item.return_value = {}
        for data in [[], {"message": " "}, {"message": 4}, {"message": "x" * 2001}, {"message": "ok", "name": " "}, {"message": "ok", "name": "x" * 41}, {"message": "ok", "name": "Guest", "token": "unknown"}, {"message": "ok", "token": 1}]:
            with self.subTest(data=data):
                self.assertEqual(self.submit(data)["type"], "error")
        self.history.put_item.assert_not_called()

    def test_failed_or_missing_storage_never_claims_success_or_stops_game(self):
        self.history.put_item.side_effect = OSError("private internal details")
        reply = self.submit({"message": "Bug", "name": "Guest"})
        self.assertEqual(reply["type"], "error")
        self.assertNotIn("private internal", reply["message"])
        self.assertFalse(self.server.failed)
        self.server.store = None
        self.assertEqual(self.submit({"message": "Bug", "name": "Guest"})["type"], "error")

    def test_feedback_still_works_when_game_has_stopped(self):
        self.server.failed = True
        self.assertEqual(self.submit({"message": "Game stopped", "name": "Guest"})["type"], "feedback_saved")
