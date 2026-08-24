"""HTTP-layer tests: auth endpoints, scenario path validation, guards.

These exercise the FastAPI app end-to-end against a throwaway temp SQLite DB
(patched settings + lifespan) with a dummy LLM key — fully offline.
"""
import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

# Must be set before `main`/`config` are imported so a bare clone without
# backend/.env can still construct the (offline) LLM stubs.
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy-for-tests")
os.environ.setdefault("JWT_SECRET", "test-secret-for-unittest")

import main  # noqa: E402
from services.ratelimit import rate_limiter  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402


class ApiTest(TestCase):
    def setUp(self):
        rate_limiter._hits.clear()  # reset the global fixed-window buckets
        self.tmp = tempfile.TemporaryDirectory()
        self.enterContext(self.tmp)
        self.enterContext(
            patch.object(main.settings, "db_path", os.path.join(self.tmp.name, "test.db"))
        )
        self.enterContext(
            patch.object(main.settings, "audio_dir", os.path.join(self.tmp.name, "audio"))
        )
        self.enterContext(
            patch.object(main.settings, "tts_cache_dir", os.path.join(self.tmp.name, "tts"))
        )
        # Context-managed TestClient runs lifespan → init_db with the temp path.
        self.client = self.enterContext(TestClient(main.app))

    def _register(self, name: str) -> str:
        r = self.client.post(
            "/api/auth/register", json={"username": name, "password": "pw1234"}
        )
        self.assertEqual(r.status_code, 200)
        return r.json()["token"]

    def test_register_login_me(self):
        c = self.client
        r = c.post("/api/auth/register", json={"username": "alice", "password": "pw1234"})
        self.assertEqual(r.status_code, 200)
        token = r.json()["token"]
        self.assertTrue(token)

        # duplicate username → 409
        r2 = c.post("/api/auth/register", json={"username": "alice", "password": "pw1234"})
        self.assertEqual(r2.status_code, 409)

        # login ok / wrong password
        self.assertEqual(
            c.post("/api/auth/login", json={"username": "alice", "password": "pw1234"}).status_code,
            200,
        )
        self.assertEqual(
            c.post("/api/auth/login", json={"username": "alice", "password": "wrong"}).status_code,
            401,
        )

        # /me with + without token
        r5 = c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r5.status_code, 200)
        self.assertEqual(r5.json()["username"], "alice")
        self.assertEqual(c.get("/api/auth/me").status_code, 401)

    def test_scenario_path_traversal_blocked(self):
        c = self.client
        # unauthenticated → 401 (endpoint now requires login)
        self.assertEqual(c.get("/api/scenarios/%2e%2e%5c%2e%2e%5cconfig").status_code, 401)

        token = self._register("bob")
        auth = {"Authorization": f"Bearer {token}"}
        # traversal id → 400 (whitelist rejects)
        r2 = c.get("/api/scenarios/..%5C..%5Cconfig", headers=auth)
        self.assertEqual(r2.status_code, 400)
        # valid-shaped but missing id → 404
        self.assertEqual(c.get("/api/scenarios/does_not_exist", headers=auth).status_code, 404)

    def test_auth_ip_rate_limit(self):
        c = self.client
        for i in range(10):
            r = c.post("/api/auth/register", json={"username": f"u{i}", "password": "pw1234"})
            self.assertEqual(r.status_code, 200)
        r = c.post("/api/auth/register", json={"username": "u11", "password": "pw1234"})
        self.assertEqual(r.status_code, 429)

    def test_tts_preview_requires_text(self):
        token = self._register("carol")
        r = self.client.post(
            "/api/tts/preview",
            json={"text": "", "voice": "x5_lingxiaotang_flow", "speed": 50},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r.status_code, 422)

    def test_history_progress_endpoint(self):
        c = self.client
        self.assertEqual(c.get("/api/history/progress").status_code, 401)
        token = self._register("dave")
        r = c.get("/api/history/progress", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["groups"], [])


if __name__ == "__main__":
    import unittest

    unittest.main()
