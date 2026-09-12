import unittest
from fastapi.testclient import TestClient
import main
from main import app, GameServer


class WebSocketTests(unittest.TestCase):
    def setUp(self):
        main.server = GameServer()
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def join(self, ws, name, token=None):
        ws.send_json({"type": "join", "name": name, "token": token})
        session = ws.receive_json()
        state = ws.receive_json()
        self.assertEqual(session["type"], "session")
        self.assertEqual(state["type"], "state")
        return session, state["state"]

    def test_health(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})

    def test_validation_and_reconnect(self):
        with self.client.websocket_connect("/ws") as a:
            session, state = self.join(a, "Alice")
            a.send_text("{bad")
            self.assertEqual(a.receive_json()["type"], "error")
            a.receive_json()
            a.send_json({"type": "join", "name": "Duplicate"})
            self.assertEqual(a.receive_json()["type"], "error")
            a.receive_json()
        with self.client.websocket_connect("/ws") as a:
            resumed, state = self.join(a, "Ignored", session["token"])
            self.assertEqual(resumed["id"], session["id"])
            self.assertEqual(len(state["players"]), 1)

    def test_all_connections_share_one_global_game(self):
        # Even old room URLs must connect to the same game.
        with self.client.websocket_connect("/ws?room=alpha") as a:
            session, _ = self.join(a, "Alice")
            with self.client.websocket_connect("/ws?room=beta") as b:
                _, state = self.join(b, "Bob")
                self.assertEqual(len(state["players"]), 2)
                self.assertEqual(state["host"], session["id"])
                self.assertEqual(len(a.receive_json()["state"]["players"]), 2)
                a.send_json({"type": "start"})
                aa, bb = a.receive_json()["state"], b.receive_json()["state"]
                self.assertEqual(aa["hand_number"], bb["hand_number"])
                self.assertEqual(aa["players"], bb["players"])
                self.assertEqual(aa["pot"], 15)

    def test_multiplayer_hand_and_rejected_actions(self):
        with self.client.websocket_connect("/ws") as a:
            sa, _ = self.join(a, "Alice")
            with self.client.websocket_connect("/ws") as b:
                sb, _ = self.join(b, "Bob")
                a.receive_json()
                b.send_json({"type": "start"})
                self.assertEqual(b.receive_json()["type"], "error")
                a.receive_json()
                b.receive_json()
                a.send_json({"type": "start"})
                aa, bb = a.receive_json()["state"], b.receive_json()["state"]
                self.assertNotEqual(aa["hand"], bb["hand"])
                b.send_json({"type": "fold"})
                self.assertEqual(b.receive_json()["type"], "error")
                a.receive_json()
                b.receive_json()
                a.send_json({"type": "set_stack", "amount": 999})
                self.assertEqual(a.receive_json()["type"], "error")
                a.receive_json()
                b.receive_json()
                sockets = {sa["id"]: a, sb["id"]: b}
                while aa["running"]:
                    sockets[aa["actor"]].send_json({"type": "check_call"})
                    aa, bb = a.receive_json()["state"], b.receive_json()["state"]
                self.assertEqual(len(aa["board"]), 5)
                self.assertEqual(sum(p["stack"] for p in aa["players"]), 2000)
                self.assertEqual(aa["result"], bb["result"])

    def test_session_takeover_keeps_seat_and_hand(self):
        with self.client.websocket_connect("/ws") as old:
            session, _ = self.join(old, "Alice")
            with self.client.websocket_connect("/ws") as bob:
                self.join(bob, "Bob")
                old.receive_json()
                old.send_json({"type": "start"})
                before = old.receive_json()["state"]
                bob.receive_json()
                with self.client.websocket_connect("/ws") as new:
                    replacement, state = self.join(new, "Alice", session["token"])
                    self.assertEqual(replacement["id"], session["id"])
                    self.assertEqual(state["hand"], before["hand"])
                    self.assertEqual(state["actor"], before["actor"])
                    self.assertFalse(state["players"][0]["folded"])
                    self.assertEqual(old.receive()["code"], 4001)
                    bob.receive_json()

    def test_unjoined_and_nonobject_messages(self):
        with self.client.websocket_connect("/ws") as ws:
            for payload in [[], {"type": "fold"}, {"type": "join", "name": None}]:
                ws.send_json(payload)
                self.assertEqual(ws.receive_json()["type"], "error")
            self.join(ws, "Recovered")
            ws.send_json({"type": []})
            self.assertEqual(ws.receive_json()["type"], "error")
            ws.receive_json()
            ws.send_bytes(b"binary")
            self.assertEqual(ws.receive_json()["type"], "error")
            ws.send_json({"type": "chat", "text": "Still connected"})
            self.assertEqual(ws.receive_json()["type"], "state")


class BroadcastTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_peer_is_folded_without_dropping_healthy_peer(self):
        from starlette.websockets import WebSocketDisconnect

        class Socket:
            def __init__(self, fail=False):
                self.fail = fail
                self.messages = []

            async def send_json(self, message):
                if self.fail:
                    raise WebSocketDisconnect()
                self.messages.append(message)

            async def close(self, code=1000):
                pass

        server = GameServer()
        a, b = server.table.join("Alice"), server.table.join("Bob")
        healthy, broken = Socket(), Socket(True)
        server.sockets = {a.id: healthy, b.id: broken}
        server.table.start(a.id)
        await server.broadcast()
        self.assertEqual(list(server.sockets), [a.id])
        self.assertFalse(b.connected)
        self.assertEqual(healthy.messages[-1]["state"]["street"], "complete")
        self.assertEqual(sum(p.stack for p in server.table.players), 2000)
