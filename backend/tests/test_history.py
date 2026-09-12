import asyncio
from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest.mock import Mock, patch

import boto3
from botocore.stub import ANY, Stubber
from fastapi.testclient import TestClient

import main
from archive import archive_items, decode, query_records
from export_history import player_report
from game import InvalidAction, Table
from storage import DynamoStore, StorageError, restore, snapshot


class MemoryArchive:
    """Checkpoint, events and identities share a durable test boundary."""

    def __init__(self):
        self.payload = None
        self.events = []
        self.profiles = {}

    def load(self):
        return restore(self.payload) if self.payload else Table()

    def identity(self, token):
        return self.profiles.get(sha256(token.encode()).hexdigest())

    def save(self, payload, events=(), profiles=None):
        self.payload = payload
        self.events.extend(deepcopy(events))
        self.profiles.update(deepcopy(profiles or {}))


class HistoryTests(unittest.TestCase):
    def test_runout_reconstruction_profit_and_privacy(self):
        table = Table()
        a, b = table.join("Alice"), table.join("Bob")
        table.set_stack(a.id, 200)
        table.set_stack(b.id, 200)
        table.start(a.id)
        start = deepcopy(table.hand_start)
        table.act(table.actor, "raise", 200)
        table.act(table.actor, "check_call")
        completed = next(e for e in table.events if e["type"] == "hand_completed")
        deck = start["deck_order"]
        self.assertEqual(start["players"][0]["hand"], deck[:2])
        self.assertEqual(start["players"][1]["hand"], deck[2:4])
        self.assertEqual(completed["board"], deck[5:8] + [deck[9], deck[11]])
        self.assertEqual(
            [e["street"] for e in table.events if e["type"] == "board_dealt"],
            ["flop", "turn", "river"],
        )
        self.assertEqual(sum(completed["net"].values()), 0)
        self.assertEqual(completed["net"][a.id], a.stack - 200)
        self.assertEqual(start["players"][0]["stack"], 200)
        items = list(archive_items(table.events))
        report = player_report([r for r in items if r["pk"] == f"PLAYER#{a.id}"])
        self.assertEqual(report["net"], a.stack - 200)
        self.assertEqual(report["completed_hands"], 1)
        self.assertNotIn(a.token, json.dumps(table.events))
        self.assertNotIn(b.token, json.dumps(table.state(a.id)))
        self.assertNotIn("deck_order", json.dumps(table.state(a.id)))
        self.assertEqual(len(set((r["pk"], r["sk"]) for r in items)), len(items))

    def test_invalid_action_and_forced_fold(self):
        table = Table()
        a, b = table.join("A"), table.join("B")
        table.start(a.id)
        before = deepcopy(table.events)
        with self.assertRaises(InvalidAction):
            table.act(b.id, "raise", 50)
        self.assertEqual(table.events, before)
        table.disconnect(a.id)
        forced = [e for e in table.events if e.get("reason") == "disconnect"]
        self.assertEqual(forced[0]["action"], "fold")
        self.assertEqual(forced[0]["player_id"], a.id)

    def test_identity_survives_seat_pruning_and_restart(self):
        store = MemoryArchive()
        server = main.GameServer(store=store)
        a = asyncio.run(server.join("A", None))
        first_session = server.table.session_id
        asyncio.run(server.checkpoint())
        server.table.disconnect(a.id)
        asyncio.run(server.checkpoint())
        server.table.join("B")
        asyncio.run(server.checkpoint())
        self.assertNotIn(a, server.table.players)
        restarted = main.GameServer(store=store, table=store.load())
        asyncio.run(restarted.checkpoint())
        returned = asyncio.run(restarted.join("A", a.token))
        asyncio.run(restarted.checkpoint())
        self.assertEqual(returned.id, a.id)
        self.assertNotEqual(restarted.table.session_id, first_session)
        self.assertEqual(returned.stack, 1000)
        self.assertTrue(any(e["type"] == "session_ended" for e in store.events))
        sequences = [e["sequence"] for e in store.events]
        self.assertEqual(sequences, sorted(set(sequences)))

    def test_restart_refunds_without_duplicate_hand_results(self):
        table = Table()
        a, b = table.join("A"), table.join("B")
        table.start(a.id)
        hand_id = table.hand_id
        recovered = restore(snapshot(table))
        cancel = next(e for e in recovered.events if e["type"] == "hand_cancelled")
        self.assertEqual(cancel["hand_id"], hand_id)
        self.assertEqual(cancel["net"], {a.id: 0, b.id: 0})
        self.assertEqual(cancel["contributions"], {a.id: 5, b.id: 10})
        self.assertEqual([p.stack for p in recovered.players], [1000, 1000])
        again = restore(snapshot(recovered))
        self.assertFalse(any(e["type"] == "hand_cancelled" for e in again.events))
        recovered.join("A", a.token)
        recovered.join("B", b.token)
        recovered.start(a.id)
        recovered.act(recovered.actor, "fold")
        final = restore(snapshot(recovered))
        self.assertFalse(any(e["type"] == "hand_cancelled" for e in final.events))
        self.assertEqual(
            [p.stack for p in final.players], [p.stack for p in recovered.players]
        )

    def test_legacy_checkpoint_marks_missing_history(self):
        table = Table()
        a = table.join("A")
        data = json.loads(snapshot(table))
        data["schema"] = 1
        for key in ("session_id", "hand_id", "hand_start", "event_sequence"):
            data.pop(key)
        data["players"][0].pop("session_id")
        recovered = restore(json.dumps(data))
        self.assertEqual(recovered.players[0].id, a.id)
        self.assertEqual(recovered.events[0]["type"], "history_started")
        self.assertFalse(any(e["type"] == "hand_completed" for e in recovered.events))
        self.assertEqual(json.loads(snapshot(recovered))["schema"], 2)

    def test_chip_movements_balance_closed_sessions(self):
        table = Table()
        a = table.join("A")
        table.join("B")
        table.set_stack(a.id, 1500)
        table.start(a.id)
        table.act(table.actor, "fold")
        table.disconnect(a.id)
        table.join("C")
        for p in list(table.players):
            table.disconnect(p.id)
        movements, net = {}, {}
        for event in table.events:
            if event["type"] in {"chips_added", "chips_removed"}:
                pid = event["player_id"]
                movements[pid] = movements.get(pid, 0) + event["amount"] * (
                    1 if event["type"] == "chips_added" else -1
                )
            if event["type"] == "hand_completed":
                for pid, amount in event["net"].items():
                    net[pid] = net.get(pid, 0) + amount
        self.assertTrue(
            all(total + net.get(pid, 0) == 0 for pid, total in movements.items())
        )

    def test_lifetime_report_separates_sessions_and_chip_movements(self):
        table = Table()
        a, b = table.join("A"), table.join("B")
        first_session = table.session_id
        table.start(a.id)
        table.act(table.actor, "fold")
        table.disconnect(a.id)
        table.disconnect(b.id)
        table.join("A", a.token)
        table.join("B", b.token)
        second_session = table.session_id
        table.set_stack(a.id, 5000)
        table.start(a.id)
        table.act(table.actor, "fold")
        records = [
            r for r in archive_items(table.events) if r["pk"] == f"PLAYER#{a.id}"
        ]
        report = player_report(
            [decode(r["payload"]) if "payload" in r else r for r in records]
        )
        self.assertEqual(report["sessions"], {first_session: -5, second_session: 5})
        self.assertEqual(report["net"], 0)
        self.assertEqual(report["completed_hands"], 2)

    def test_all_chat_is_archived_but_live_log_is_bounded(self):
        table = Table()
        table.join("A")
        for i in range(120):
            table.log(f"chat {i}")
        self.assertEqual(len(table.history), 100)
        messages = [e for e in table.events if e["type"] == "message"]
        self.assertEqual(len(messages), 120)
        self.assertEqual(messages[0]["text"], "chat 0")

    def test_ambiguous_commit_stops_play_and_preserves_one_result(self):
        store = MemoryArchive()
        main.server = main.GameServer(store=store)
        with TestClient(main.app) as client:
            with (
                client.websocket_connect("/ws") as a,
                client.websocket_connect("/ws") as b,
            ):
                a.send_json({"type": "join", "name": "A"})
                a.receive_json()
                a.receive_json()
                b.send_json({"type": "join", "name": "B"})
                b.receive_json()
                b.receive_json()
                a.receive_json()
                a.send_json({"type": "start"})
                a.receive_json()
                b.receive_json()
                original_save = store.save

                def uncertain(*args):
                    original_save(*args)
                    raise OSError("response lost after commit")

                store.save = uncertain
                a.send_json({"type": "fold"})
                self.assertEqual(a.receive()["code"], 1011)
                self.assertEqual(client.get("/health").status_code, 503)
        store.save = original_save
        main.server = main.GameServer(store=store)
        with TestClient(main.app):
            pass
        self.assertEqual(
            len([e for e in store.events if e["type"] == "hand_completed"]), 1
        )
        self.assertFalse(any(e["type"] == "hand_cancelled" for e in store.events))


class DynamoHistoryTests(unittest.TestCase):
    def test_sdk_transaction_serialization_and_duplicate_save(self):
        resource = boto3.Session(
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name="us-east-1",
        ).resource("dynamodb")
        store = DynamoStore(resource.Table("game"), resource.Table("history"))
        table = Table()
        table.join("Alice")
        payload = snapshot(table)
        with Stubber(resource.meta.client) as stub:
            stub.add_response(
                "transact_write_items",
                {},
                {"TransactItems": ANY, "ClientRequestToken": ANY},
            )
            store.save(payload, table.events, table.profiles)
            store.save(payload)
            stub.assert_no_pending_responses()
        self.assertEqual(store.version, 1)

    def test_atomic_transaction_shapes_and_failed_write_version(self):
        db, history = Mock(), Mock()
        db.name, history.name = "game", "history"
        store = DynamoStore(db, history)
        table = Table()
        table.join("A")
        store.save(snapshot(table), table.events, table.profiles)
        writes = db.meta.client.transact_write_items.call_args.kwargs["TransactItems"]
        self.assertEqual(writes[0]["Put"]["Item"]["pk"], "GAME#GLOBAL")
        self.assertTrue(
            any(w["Put"]["Item"]["pk"].startswith("IDENTITY#") for w in writes)
        )
        self.assertTrue(all("ConditionExpression" in w["Put"] for w in writes))
        first_payload = store.last_payload
        db.meta.client.transact_write_items.side_effect = OSError("failed")
        table.log("not committed")
        with self.assertRaises(OSError):
            store.save(snapshot(table), table.events)
        self.assertEqual(store.version, 1)
        self.assertEqual(store.last_payload, first_payload)

    def test_queries_read_all_pages(self):
        table = Mock()
        table.name = "history"
        engine = Table()
        engine.join("A")
        records = list(archive_items(engine.events))
        table.meta.client.get_paginator.return_value.paginate.return_value = [
            {"Items": records[:1]},
            {"Items": records[1:]},
        ]
        result = list(query_records(table, "SESSION#example", "EVENT#"))
        self.assertEqual(len(result), len(records))
        self.assertEqual(result[0], decode(records[0]["payload"]))

    def test_history_configuration_required(self):
        with patch.dict(
            "os.environ", {"DYNAMODB_TABLE": "game", "DYNAMODB_HISTORY_TABLE": ""}
        ):
            with self.assertRaises(StorageError):
                DynamoStore.from_env()

    def test_identity_failure_does_not_create_a_different_player(self):
        server = main.GameServer(
            store=Mock(identity=Mock(side_effect=OSError("offline")))
        )
        with self.assertRaises(StorageError):
            asyncio.run(server.join("A", "previous-identity"))
        self.assertEqual(server.table.players, [])


if __name__ == "__main__":
    unittest.main()
