"""Private append-only history records and query helpers (never browser views)."""

import json
import zlib
from boto3.dynamodb.conditions import Attr, ConditionExpressionBuilder, Key


def encode(value):
    data = zlib.compress(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    )
    if len(data) > 350_000:
        raise ValueError("History record exceeds the storage limit.")
    return data


def decode(value):
    return json.loads(zlib.decompress(bytes(value)))


def expression(condition, key=False):
    """Compile builders for transaction/paginator APIs that accept strings only."""
    built = ConditionExpressionBuilder().build_expression(
        condition, is_key_condition=key
    )
    result = {
        "KeyConditionExpression"
        if key
        else "ConditionExpression": built.condition_expression,
        "ExpressionAttributeNames": built.attribute_name_placeholders,
    }
    if built.attribute_value_placeholders:
        result["ExpressionAttributeValues"] = built.attribute_value_placeholders
    return result


def archive_items(events):
    for event in events:
        sequence = f"{event['sequence']:020d}"
        session_id, hand_id = event["session_id"], event["hand_id"]
        item = {"sk": f"EVENT#{sequence}", "payload": encode(event)}
        if session_id:
            yield {"pk": f"SESSION#{session_id}", **item}
        else:
            # Changes to retained seats between sessions still have an audit trail.
            yield {"pk": "SYSTEM", **item}
        if hand_id:
            yield {"pk": f"HAND#{hand_id}", **item}
        if event["type"] in {"session_started", "session_ended", "history_started"}:
            yield {
                "pk": "SESSIONS",
                "sk": f"{event['at']}#{sequence}",
                "payload": encode(event),
            }
        if event["type"] in {"hand_completed", "hand_cancelled"}:
            yield {"pk": f"HAND#{hand_id}", "sk": "SUMMARY", "payload": encode(event)}
            for player_id, net in event["net"].items():
                player = next(p for p in event["players"] if p["id"] == player_id)
                yield {
                    "pk": f"PLAYER#{player_id}",
                    "sk": f"RESULT#{event['at']}#{hand_id}",
                    "player_id": player_id,
                    "name": player["name"],
                    "session_id": session_id,
                    "hand_id": hand_id,
                    "status": event["type"],
                    "net": net,
                    "ending_stack": player["stack"],
                    "at": event["at"],
                }
        if event["type"] in {"chips_added", "chips_removed"}:
            yield {
                "pk": f"PLAYER#{event['player_id']}",
                "sk": f"MOVEMENT#{event['at']}#{sequence}",
                "payload": encode(event),
            }


def transaction_put(table_name, item, condition=None):
    return {
        "Put": {
            "TableName": table_name,
            "Item": item,
            **expression(
                condition if condition is not None else Attr("pk").not_exists()
            ),
        }
    }


def query_records(table, partition, prefix=None):
    condition = Key("pk").eq(partition)
    if prefix:
        condition &= Key("sk").begins_with(prefix)
    pages = table.meta.client.get_paginator("query").paginate(
        TableName=table.name, ConsistentRead=True, **expression(condition, key=True)
    )
    for page in pages:
        for item in page.get("Items", []):
            yield decode(item["payload"]) if "payload" in item else item
