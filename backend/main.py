"""Run locally with python run.py to load the backend .env settings."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from game import Table, InvalidAction
from storage import DynamoStore, StorageError, snapshot
from fastapi.responses import JSONResponse
from feedback import feedback_connection


@asynccontextmanager
async def lifespan(app):
    if server.store is None:
        server.store = DynamoStore.from_env()
    if server.store:
        server.table = await asyncio.to_thread(server.store.load)
        await server.checkpoint()
    try:
        yield
    finally:
        if server.deal_task:
            server.deal_task.cancel()
            await asyncio.gather(server.deal_task, return_exceptions=True)


app = FastAPI(lifespan=lifespan)


@dataclass
class GameServer:
    table: Table = field(default_factory=Table)
    sockets: dict = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    store: object = None
    failed: bool = False
    deal_task: asyncio.Task | None = None
    auto_deal_delay: float = 5

    def can_auto_deal(self):
        return (not self.failed and self.table.auto_deal
                and self.table.street == "complete"
                and sum(p.connected and p.stack > 0 for p in self.table.players) >= 2)

    def schedule_deal(self):
        if not self.can_auto_deal():
            if self.deal_task:
                self.deal_task.cancel()
                self.deal_task = None
        elif self.deal_task is None:
            self.deal_task = asyncio.create_task(self.deal_next())

    async def deal_next(self):
        try:
            await asyncio.sleep(self.auto_deal_delay)
            async with self.lock:
                self.deal_task = None
                if self.can_auto_deal():
                    self.table.start(next(p.id for p in self.table.players if p.connected))
                    await self.broadcast()
        except StorageError:
            pass

    async def checkpoint(self):
        if self.failed:
            raise StorageError("Storage unavailable; restart the backend to recover.")
        if self.store:
            try:
                await asyncio.to_thread(
                    self.store.save,
                    snapshot(self.table),
                    self.table.events,
                    self.table.profiles,
                )
            except Exception as exc:
                self.failed = True
                logging.error(
                    "Game persistence failed (%s); stopping play.", type(exc).__name__
                )
                peers = list(self.sockets.values())
                self.sockets.clear()
                await asyncio.gather(*(self.close(peer, code=1011) for peer in peers))
                raise StorageError(
                    "Storage unavailable; restart the backend to recover."
                ) from exc

        self.table.events.clear()
        self.table.profiles.clear()

    async def join(self, name, token):
        profile = None
        if token is not None and (not isinstance(token, str) or len(token) > 128):
            raise InvalidAction("Invalid player identity.")
        if (
            token
            and self.store
            and not any(p.token == token for p in self.table.players)
        ):
            try:
                profile = await asyncio.to_thread(self.store.identity, token)
            except Exception as exc:
                # Do not silently assign a different lifetime identity on a read failure.
                raise StorageError(
                    "Player history unavailable; reconnect to retry."
                ) from exc
        return self.table.join(name, token, profile)

    @staticmethod
    async def close(socket, code=1000):
        try:
            await asyncio.wait_for(socket.close(code=code), timeout=2)
        except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
            pass

    async def broadcast(self):
        await self.checkpoint()

        async def send(pid, socket):
            try:
                await asyncio.wait_for(
                    socket.send_json({"type": "state", "state": self.table.state(pid)}),
                    timeout=2,
                )
            except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
                return pid, socket
            return None

        # Called under the game lock. A failed peer must not disconnect the actor
        # whose action triggered this broadcast. Repair state and notify survivors.
        while self.sockets:
            failures = [
                failure
                for failure in await asyncio.gather(
                    *(send(pid, socket) for pid, socket in list(self.sockets.items()))
                )
                if failure
            ]
            if not failures:
                break
            for pid, socket in failures:
                if self.sockets.get(pid) is socket:
                    del self.sockets[pid]
                    self.table.disconnect(pid)
            await asyncio.gather(*(self.close(socket) for _, socket in failures))
            await self.checkpoint()

        self.schedule_deal()


server = GameServer()


@app.get("/health")
def health():
    if server.failed:
        return JSONResponse({"status": "storage_unavailable"}, status_code=503)
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    if server.failed:
        await server.close(websocket, code=1011)
        return
    player = None
    try:
        while True:
            packet = await websocket.receive()
            if packet["type"] == "websocket.disconnect":
                break
            raw = packet.get("text")
            if raw is None:
                await websocket.send_json(
                    {"type": "error", "message": "Send JSON text, not binary data."}
                )
                continue
            if len(raw) > 4096:
                await websocket.send_json(
                    {"type": "error", "message": "Message is too large."}
                )
                continue
            async with server.lock:
                if server.failed:
                    break
                try:
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise InvalidAction("Expected a JSON object.")
                    kind = data.get("type")
                    if not isinstance(kind, str):
                        raise InvalidAction("Message type must be a string.")
                    if player and server.sockets.get(player.id) is not websocket:
                        raise InvalidAction("This seat is connected in another window.")
                    if kind == "join":
                        if player:
                            raise InvalidAction("You have already joined.")
                        player = await server.join(data.get("name"), data.get("token"))
                        old = server.sockets.get(player.id)
                        server.sockets[player.id] = websocket
                        await server.checkpoint()
                        if old and old is not websocket:
                            await server.close(old, code=4001)
                        await websocket.send_json(
                            {"type": "session", "token": player.token, "id": player.id}
                        )
                    elif not player:
                        raise InvalidAction("Join the table first.")
                    elif kind == "start":
                        server.table.start(player.id)
                    elif kind in {"fold", "check_call", "raise"}:
                        server.table.act(player.id, kind, data.get("amount"))
                    elif kind == "settings":
                        server.table.set_settings(player.id, data.get("small_blind"),
                                                  data.get("big_blind"), data.get("auto_deal"),
                                                  data.get("cents"))
                    elif kind == "move_seat":
                        server.table.move_seat(player.id, data.get("seat"))
                    elif kind == "kick":
                        target_id = data.get("player_id")
                        server.table.kick(player.id, target_id)
                        # Persist removal before acknowledging it or closing the peer.
                        await server.checkpoint()
                        removed = server.sockets.pop(target_id, None)
                        if removed:
                            await server.close(removed, code=4002)
                    elif kind == "set_stack":
                        server.table.set_stack(player.id, data.get("amount"))
                    elif kind == "chat":
                        message = data.get("text")
                        if (
                            not isinstance(message, str)
                            or not 1 <= len(message.strip()) <= 300
                        ):
                            raise InvalidAction("Chat must contain 1–300 characters.")
                        server.table.log(
                            f"{player.name}: {message.strip()}", player_id=player.id
                        )
                    else:
                        raise InvalidAction("Unknown message type.")
                except (InvalidAction, json.JSONDecodeError) as exc:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": str(exc)
                            if isinstance(exc, InvalidAction)
                            else "Invalid JSON.",
                        }
                    )
                await server.broadcast()
    except StorageError:
        await server.close(websocket, code=1011)
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    finally:
        async with server.lock:
            if (
                not server.failed
                and player
                and server.sockets.get(player.id) is websocket
            ):
                del server.sockets[player.id]
                server.table.disconnect(player.id)
                try:
                    await server.broadcast()
                except StorageError:
                    pass


@app.websocket("/feedback")
async def feedback_endpoint(websocket: WebSocket):
    await feedback_connection(websocket, server)
