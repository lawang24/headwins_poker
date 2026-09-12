"""Private, versioned checkpoints for the single game process."""

import json
import os
import zlib
from dataclasses import asdict

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.config import Config

from game import Player, Table


class StorageError(RuntimeError):
    pass


def snapshot(table):
    return json.dumps(
        {
            "schema": 1,
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
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


def restore(payload):
    data = json.loads(payload)
    if data["schema"] != 1:
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
    for player in table.players:
        player.connected = False
        if data["running"]:
            player.stack += player.contribution
            player.hand = []
            player.in_hand = player.folded = False
            player.committed = player.contribution = 0
            player.acted_at = None
    if data["running"]:
        table.street, table.board, table.result = "waiting", [], None
        table.log(
            "Server restarted. Unfinished hand cancelled; committed chips returned."
        )
    return table


class DynamoStore:
    def __init__(self, table):
        self.table = table
        self.version = 0
        self.last_payload = None

    @classmethod
    def from_env(cls):
        name = os.environ.get("DYNAMODB_TABLE")
        if not name:
            return None
        resource = boto3.Session().resource(
            "dynamodb",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            config=Config(
                connect_timeout=3,
                read_timeout=5,
                retries={"mode": "standard", "total_max_attempts": 3},
            ),
        )
        return cls(resource.Table(name))

    def load(self):
        item = self.table.get_item(Key={"pk": "GAME#GLOBAL"}, ConsistentRead=True).get(
            "Item"
        )
        if not item:
            return Table()
        self.version = int(item["version"])
        payload = zlib.decompress(bytes(item["payload"])).decode("utf-8")
        return restore(payload)

    def save(self, payload):
        if payload == self.last_payload:
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
        self.table.put_item(
            Item={
                "pk": "GAME#GLOBAL",
                "version": self.version + 1,
                "payload": compressed,
            },
            ConditionExpression=condition,
        )
        self.version += 1
        self.last_payload = payload
