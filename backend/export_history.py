"""Authorized offline history export; no public endpoint exposes private cards."""

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from archive import query_records
from storage import DynamoStore, StorageError


def player_report(records):
    results = [r for r in records if r.get("sk", "").startswith("RESULT#")]
    sessions = {r["session_id"]: 0 for r in records if r.get("session_id") is not None}
    for result in results:
        sid = result["session_id"]
        sessions[sid] = sessions.get(sid, 0) + int(result["net"])
    return {
        "net": sum(int(r["net"]) for r in results),
        "completed_hands": sum(r["status"] == "hand_completed" for r in results),
        "cancelled_hands": sum(r["status"] == "hand_cancelled" for r in results),
        "sessions": sessions,
        "records": records,
    }


def json_number(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Cannot export {type(value).__name__}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sessions", action="store_true")
    group.add_argument("--system", action="store_true")
    group.add_argument("--session")
    group.add_argument("--hand")
    group.add_argument("--player")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New private JSON file; existing files are not overwritten",
    )
    args = parser.parse_args()
    load_dotenv(Path(__file__).with_name(".env"))
    store = DynamoStore.from_env()
    if store is None:
        raise StorageError("Configure DynamoDB to export permanent history.")
    partition = (
        "SYSTEM"
        if args.system
        else "SESSIONS"
        if args.sessions
        else f"SESSION#{args.session}"
        if args.session
        else f"HAND#{args.hand}"
        if args.hand
        else f"PLAYER#{args.player}"
    )
    records = list(query_records(store.history_table, partition))
    result = player_report(records) if args.player else records
    # Exclusive creation and owner-only permissions protect private cards in exports.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(result, output, ensure_ascii=False, indent=2, default=json_number)
        output.write("\n")


if __name__ == "__main__":
    main()
