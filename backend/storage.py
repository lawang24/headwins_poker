"""Private, versioned checkpoints for the single game process."""

import json
import os
import zlib
from dataclasses import asdict
from hashlib import sha256
from uuid import uuid4

from archive import archive_items, transaction_put

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.config import Config

from game import Player, Table


class StorageError(RuntimeError):
    pass


def snapshot(table):
    return json.dumps(
        {
            "schema": 2,
            "session_id": table.session_id,
            "hand_id": table.hand_id,
            "hand_start": table.hand_start,
            "event_sequence": table.event_sequence,
            "players": [asdict(p) for p in table.players],
            "running": table.running,
            "dealer": table.dealer,
            "hand_number": table.hand_number,
            "history": table.history,
            "result": table.result,
            "board": table.board,
            "street": table.street,
            "small_blind": table.small_blind,
            "big_blind": table.big_blind,
            "auto_deal": table.auto_deal,
            "cents": table.cents,
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


def restore(payload):
    data = json.loads(payload)
    if data["schema"] not in {1, 2}:
        raise StorageError("Unsupported checkpoint schema.")
    table = Table()
    table.players = [Player(**p) for p in data["players"]]
    for key in (
        "dealer",
        "hand_number",
        "history",
        "result",
        "board",
        "street",
        "small_blind",
        "big_blind",
    ):
        setattr(table, key, data[key])
    table.auto_deal = data.get("auto_deal", False)
    table.cents = data.get("cents", False)
    table.session_id = data.get("session_id")
    table.hand_id = data.get("hand_id")
    table.hand_start = data.get("hand_start")
    table.event_sequence = data.get("event_sequence", 0)
    if data["schema"] == 1 and table.players:
        table.session_id = uuid4().hex
        for player in table.players:
            player.session_id = table.session_id
        table.record(
            "history_started",
            reason="legacy_checkpoint",
            players=table.private_players(),
            history=table.history,
            board=table.board,
            street=table.street,
            result=table.result,
            hand_number=table.hand_number,
        )
    for player in table.players:
        table.register(player)
        player.connected = False
        if data["running"]:
            player.stack += player.contribution
            player.hand = []
            player.in_hand = player.folded = False
            player.committed = player.contribution = 0
            player.acted_at = None
    if data["running"]:
        table.hand_id = table.hand_id or uuid4().hex
        table.record(
            "hand_cancelled",
            hand_id=table.hand_id,
            reason="server_restart",
            start=table.hand_start,
            board=data["board"],
            players=table.private_players(),
            contributions={p["id"]: p["contribution"] for p in data["players"]},
            net={
                p.id: 0
                for p in table.players
                if p.id in {old["id"] for old in data["players"] if old["in_hand"]}
            },
        )
        table.street, table.board, table.result = "waiting", [], None
        table.log(
            "Server restarted. Unfinished hand cancelled; committed chips returned."
        )
    table.end_session("server_restart")
    return table


class DynamoStore:
    def __init__(self, table, history_table=None):
        self.table = table
        self.history_table = history_table
        self.version = 0
        self.last_payload = None

    @classmethod
    def from_env(cls):
        name = os.environ.get("DYNAMODB_TABLE")
        if not name:
            return None
        history_name = os.environ.get("DYNAMODB_HISTORY_TABLE")
        if not history_name:
            raise StorageError(
                "Set DYNAMODB_HISTORY_TABLE after deploying the history table."
            )
        resource = boto3.Session().resource(
            "dynamodb",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            config=Config(
                connect_timeout=3,
                read_timeout=5,
                retries={"mode": "standard", "total_max_attempts": 3},
            ),
        )
        return cls(resource.Table(name), resource.Table(history_name))

    def load(self):
        item = self.table.get_item(Key={"pk": "GAME#GLOBAL"}, ConsistentRead=True).get(
            "Item"
        )
        if not item:
            return Table()
        self.version = int(item["version"])
        payload = zlib.decompress(bytes(item["payload"])).decode("utf-8")
        return restore(payload)

    def identity(self, token):
        if not self.history_table:
            return None
        digest = sha256(token.encode()).hexdigest()
        return self.history_table.get_item(
            Key={"pk": f"IDENTITY#{digest}", "sk": "PROFILE"}, ConsistentRead=True
        ).get("Item")

    def save_feedback(self, record):
        if self.history_table is None:
            raise StorageError("Feedback storage is unavailable.")
        self.history_table.put_item(Item={
            "pk": "FEEDBACK",
            "sk": f"{record['created_at']}#{record['id']}",
            **record,
        })

    def save(self, payload, events=(), profiles=None):
        if payload == self.last_payload and not events and not profiles:
            return
        compressed = zlib.compress(payload.encode("utf-8"))
        if len(compressed) > 350_000:
            raise StorageError("Checkpoint exceeds the storage limit.")
        condition = (
            Attr("version").eq(self.version)
            if self.version
            else Attr("pk").not_exists()
        )
        # A timeout can mean a committed write. Stop the game on any failure;
        # restarting reloads the authoritative checkpoint, never blindly retries an action.
        item = {"pk": "GAME#GLOBAL", "version": self.version + 1, "payload": compressed}
        if self.history_table is not None:
            writes = [transaction_put(self.table.name, item, condition)]
            writes.extend(
                transaction_put(self.history_table.name, record)
                for record in archive_items(events)
            )
            for digest, profile in (profiles or {}).items():
                for pk in (f"IDENTITY#{digest}", f"PLAYER#{profile['player_id']}"):
                    record = {"pk": pk, "sk": "PROFILE", **profile}
                    guard = Attr("pk").not_exists() | Attr("player_id").eq(
                        profile["player_id"]
                    )
                    writes.append(
                        transaction_put(self.history_table.name, record, guard)
                    )
            if len(writes) > 100:
                raise StorageError("Too many changes for an atomic history save.")
            self.table.meta.client.transact_write_items(
                TransactItems=writes, ClientRequestToken=uuid4().hex
            )
        else:
            # Kept for checkpoint-only adapters/tests; configured servers require history.
            self.table.put_item(Item=item, ConditionExpression=condition)
        self.version += 1
        self.last_payload = payload
