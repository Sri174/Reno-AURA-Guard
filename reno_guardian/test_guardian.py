import os
import tempfile
import unittest
import time
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from .app import app, voice_token, monitor
from .core import Store, redact


class GuardianTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name+"/test.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def incident(self):
        return self.store.event("query", "Slow query", "duration 300 seconds", "critical")

    def test_dedup_and_recovery_call_reservation(self):
        a = self.incident()
        self.assertTrue(self.store.reserve_call(a["id"]))
        b = self.incident()
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(b["occurrences"], 2)
        self.assertFalse(self.store.reserve_call(a["id"]))
        self.store.resolve("query")
        self.incident()
        self.assertTrue(self.store.reserve_call(a["id"]))

    def test_approval_is_exact_once_and_superseded(self):
        a = self.incident()
        old = self.store.propose(a["id"], "first suggestion")
        new = self.store.propose(a["id"], "revised suggestion")
        with self.assertRaises(ValueError):
            self.store.approve(old["id"], old["digest"])
        with self.assertRaises(ValueError):
            self.store.approve(new["id"], "f"*64)
        self.assertEqual(self.store.approve(new["id"], new["digest"])["state"], "approved")
        with self.assertRaises(ValueError):
            self.store.approve(new["id"], new["digest"])

    def test_expired_approval(self):
        p = self.store.propose(self.incident()["id"], "suggestion")
        with self.store.connect() as db:
            db.execute("UPDATE proposals SET expires=0")
        with self.assertRaises(ValueError):
            self.store.approve(p["id"], p["digest"])

    def test_secret_redaction(self):
        self.assertNotIn("abc123", redact("password=abc123"))
        self.assertNotIn("abc123", redact("Bearer abc123"))

    def test_api_requires_auth_and_voice_rejects_invalid_grant(self):
        with patch.dict(os.environ, {"GUARDIAN_ADMIN_TOKEN": "x"*40, "GUARDIAN_HEALTH_URL": "",
                                     "GUARDIAN_CALLS_ENABLED": "false",
                                     "GUARDIAN_STATE_PATH": self.temp.name+"/api.sqlite3"}):
            with TestClient(app) as client:
                self.assertEqual(client.get("/incidents").status_code, 401)
                self.assertEqual(client.get("/").status_code, 200)
                self.assertIn("frame-ancestors 'none'", client.get("/").headers["content-security-policy"])
                response = client.post("/events", headers={"Authorization": "Bearer "+"x"*40},
                                       json={"fingerprint": "test", "title": "Example",
                                             "evidence": "redacted error", "severity": "warning"})
                self.assertEqual(response.status_code, 200)
                from starlette.websockets import WebSocketDisconnect
                with self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect("/voice/1?expires=1&token=fake"):
                        pass

    def test_tamil_voice_conversation_and_replay_rejection(self):
        with patch.dict(os.environ, {"GUARDIAN_ADMIN_TOKEN": "x"*40, "GUARDIAN_HEALTH_URL": "",
                                     "GUARDIAN_CALLS_ENABLED": "false",
                                     "GUARDIAN_STATE_PATH": self.temp.name+"/voice.sqlite3"}):
            with TestClient(app) as client:
                incident = app.state.store.event("demo", "API unavailable", "Connection refused", "warning")
                expires = int(time.time()) + 300
                url = f"/voice/{incident['id']}?expires={expires}&token={voice_token(incident['id'], expires)}"
                with patch("reno_guardian.app.answer", new=AsyncMock(return_value="Backend இணைப்பில் பிரச்சினை உள்ளது.")) as answer_mock:
                    with client.websocket_connect(url) as socket:
                        socket.send_json({"type": "prompt", "voicePrompt": "என்ன", "last": False})
                        socket.send_json({"type": "prompt", "voicePrompt": "பிரச்சினை?", "last": True})
                        reply = socket.receive_json()
                        self.assertIn("Backend", reply["token"])
                        self.assertTrue(reply["last"])
                        self.assertEqual(answer_mock.await_count, 1)
                        self.assertEqual(answer_mock.call_args.args[1][0]["content"], "என்ன பிரச்சினை?")
                        socket.send_json({"type": "interrupt", "utteranceUntilInterrupt": "Backend"})
                        socket.send_json({"type": "prompt", "voicePrompt": "சரி, அடுத்து?", "last": True})
                        socket.receive_json()
                        self.assertEqual(answer_mock.await_count, 2)
                        self.assertEqual(answer_mock.call_args.args[1][1], {"role": "assistant", "content": "Backend"})
                from starlette.websockets import WebSocketDisconnect
                with self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect(url):
                        pass

    def test_monitor_failure_threshold_and_recovery(self):
        import asyncio
        import httpx
        async def scenario():
            client = AsyncMock()
            response = httpx.Response(200, request=httpx.Request("GET", "http://example.test"))
            client.get.side_effect = [httpx.ConnectError("offline")]*3 + [response]
            context = AsyncMock()
            context.__aenter__.return_value = client
            calls = []
            async def record(store, incident):
                calls.append(incident["id"])
            counter = 0
            async def tick(seconds):
                nonlocal counter
                counter += 1
                if counter == 4:
                    raise asyncio.CancelledError()
            with patch.dict(os.environ, {"GUARDIAN_HEALTH_URL": "http://example.test"}):
                with patch("reno_guardian.app.httpx.AsyncClient", return_value=context), patch("reno_guardian.app.call_owner", side_effect=record), patch("reno_guardian.app.asyncio.sleep", side_effect=tick):
                    with self.assertRaises(asyncio.CancelledError):
                        await monitor(self.store)
            self.assertEqual(len(calls), 1)
            self.assertEqual(self.store.incidents()[0]["state"], "resolved")
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
