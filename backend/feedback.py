"""Private feedback intake, independent of game actions and checkpoints."""

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

from game import InvalidAction
from storage import StorageError


async def submit_feedback(server, data):
    if not isinstance(data, dict):
        raise InvalidAction("Expected a JSON object.")
    message = data.get("message")
    if not isinstance(message, str) or not 1 <= len(message.strip()) <= 2000:
        raise InvalidAction("Feedback must contain 1–2000 characters.")
    token = data.get("token")
    if token is not None and (not isinstance(token, str) or len(token) > 128):
        raise InvalidAction("Invalid player identity.")
    if not server.store:
        raise StorageError("Feedback storage is unavailable. Please try again later.")
    profile = None
    if token:
        async with server.lock:
            player = next((p for p in server.table.players if p.token == token), None)
            if player:
                profile = {"player_id": player.id, "name": player.name}
        if profile is None:
            profile = await asyncio.to_thread(server.store.identity, token)
        if profile is None:
            raise InvalidAction("Your player identity was not found. Rejoin the table and try again.")
    name = profile["name"] if profile else data.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
        raise InvalidAction("Please enter your name (1–40 characters).")
    record = {
        "id": uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "message": message.strip(),
        "reporter_name": name.strip(),
        "player_id": profile["player_id"] if profile else None,
        "reporter_type": "player" if profile else "guest",
    }
    await asyncio.to_thread(server.store.save_feedback, record)
    return {"type": "feedback_saved", "id": record["id"], "created_at": record["created_at"]}


async def feedback_connection(websocket, server):
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
        if len(raw) > 16000:
            raise InvalidAction("Feedback request is too large.")
        result = await submit_feedback(server, json.loads(raw))
    except (InvalidAction, json.JSONDecodeError) as exc:
        result = {"type": "error", "message": str(exc) if isinstance(exc, InvalidAction) else "Invalid JSON."}
    except Exception:
        # Neither report text nor identity credentials belong in logs/errors.
        result = {"type": "error", "message": "Could not confirm your feedback was saved. Please try again later."}
    try:
        await websocket.send_json(result)
    finally:
        await server.close(websocket)
