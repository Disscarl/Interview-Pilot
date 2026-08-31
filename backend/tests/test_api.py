"""HTTP-layer tests: auth endpoints, input caps, guards.

These exercise the FastAPI app end-to-end against a throwaway temp SQLite DB
(patched settings + lifespan) with a dummy LLM key — fully offline.
"""
import base64
import os
import tempfile
from unittest import TestCase
from unittest.mock import AsyncMock, patch

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

    def test_resume_extract_truncates_long_text(self):
        """R3: extract caps text at _MAX_JD_RESUME so analyze never 422s on a
        long resume (previously an unresolvable dead-end for the user)."""
        c = self.client
        token = self._register("resume_long")
        auth = {"Authorization": f"Bearer {token}"}
        body_payload = {
            "filename": "long.pdf",
            "data_base64": base64.b64encode(b"x").decode(),
        }

        # Extracted text over the cap → truncated + flagged.
        with patch.object(main, "extract_text", return_value="字" * 30000):
            r = c.post("/api/resume/extract", json=body_payload, headers=auth)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["text"]), main._MAX_JD_RESUME)
        self.assertTrue(body["truncated"])

        # Normal-length text passes through untouched.
        with patch.object(main, "extract_text", return_value="short resume text"):
            r2 = c.post("/api/resume/extract", json=body_payload, headers=auth)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["text"], "short resume text")
        self.assertFalse(r2.json()["truncated"])

    def test_resume_extract_corrupt_docx_returns_422(self):
        """L9: a corrupt .docx must surface as a friendly 422, not a 500."""
        c = self.client
        token = self._register("resume_bad")
        auth = {"Authorization": f"Bearer {token}"}
        r = c.post(
            "/api/resume/extract",
            json={
                "filename": "bad.docx",
                "data_base64": base64.b64encode(b"this is not a zip").decode(),
            },
            headers=auth,
        )
        self.assertEqual(r.status_code, 422)

    def test_history_progress_endpoint(self):
        c = self.client
        self.assertEqual(c.get("/api/history/progress").status_code, 401)
        token = self._register("dave")
        r = c.get("/api/history/progress", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["groups"], [])

    def test_audio_endpoint_auth_paths(self):
        """T-1: /api/audio must authenticate (query + Bearer), enforce ownership,
        reject bad paths, and 404 for missing files."""
        import asyncio

        from services.auth import decode_token
        from services.history import save_interview

        c = self.client
        token_a = self._register("audio_a")
        token_b = self._register("audio_b")
        user_a = decode_token(token_a)

        async def seed():
            await save_interview(
                "sess_audio_1", "岗位", "公司",
                [{"role": "interviewer", "content": "你好"}],
                {"overall_score": 3.0}, user_a,
            )

        asyncio.run(seed())
        audio_dir = os.path.join(main.settings.audio_dir, "sess_audio_1")
        os.makedirs(audio_dir, exist_ok=True)
        with open(os.path.join(audio_dir, "msg1.wav"), "wb") as f:
            f.write(b"RIFF-fake-wav")

        # unauthenticated → 401
        self.assertEqual(c.get("/api/audio/sess_audio_1/msg1").status_code, 401)
        # query token → 200
        self.assertEqual(
            c.get(f"/api/audio/sess_audio_1/msg1?token={token_a}").status_code, 200
        )
        # Bearer header → 200
        self.assertEqual(
            c.get(
                "/api/audio/sess_audio_1/msg1",
                headers={"Authorization": f"Bearer {token_a}"},
            ).status_code,
            200,
        )
        # other user → 404 (ownership)
        self.assertEqual(
            c.get(f"/api/audio/sess_audio_1/msg1?token={token_b}").status_code, 404
        )
        # traversal path → 400
        self.assertEqual(
            c.get(f"/api/audio/..%5Cbad/msg1?token={token_a}").status_code, 400
        )
        # missing file → 404
        self.assertEqual(
            c.get(f"/api/audio/sess_audio_1/nope?token={token_a}").status_code, 404
        )

    def test_tts_preview_branches(self):
        """T-9: too-long text → 422, synthesis failure → 502, success → 200+b64."""
        c = self.client
        token = self._register("tts_branches")
        auth = {"Authorization": f"Bearer {token}"}

        r = c.post(
            "/api/tts/preview",
            json={"text": "字" * 501, "voice": "x5_lingxiaotang_flow", "speed": 50},
            headers=auth,
        )
        self.assertEqual(r.status_code, 422)

        with patch.object(main, "synthesize_cached", new=AsyncMock(return_value=None)):
            r2 = c.post(
                "/api/tts/preview",
                json={"text": "你好", "voice": "x5_lingxiaotang_flow", "speed": 50},
                headers=auth,
            )
        self.assertEqual(r2.status_code, 502)

        with patch.object(main, "synthesize_cached", new=AsyncMock(return_value=b"mp3")):
            r3 = c.post(
                "/api/tts/preview",
                json={"text": "你好", "voice": "x5_lingxiaotang_flow", "speed": 50},
                headers=auth,
            )
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(r3.json()["audio_base64"], base64.b64encode(b"mp3").decode())

    def test_jd_analyze_branches(self):
        """T-4: validation 422s, success, candidate-failure fallback, LLM 500."""
        c = self.client
        token = self._register("jd_branches")
        auth = {"Authorization": f"Bearer {token}"}
        base = {"text": "UE开发工程师 JD", "company": "", "resume_text": "我有三年经验"}

        # empty JD → 422
        self.assertEqual(
            c.post("/api/jd/analyze", json={**base, "text": "  "}, headers=auth).status_code,
            422,
        )
        # missing resume → 422
        self.assertEqual(
            c.post("/api/jd/analyze", json={**base, "resume_text": ""}, headers=auth).status_code,
            422,
        )
        # JD too long → 422
        self.assertEqual(
            c.post(
                "/api/jd/analyze", json={**base, "text": "字" * 20001}, headers=auth
            ).status_code,
            422,
        )
        # company intro too long → 422
        self.assertEqual(
            c.post(
                "/api/jd/analyze", json={**base, "company": "字" * 2001}, headers=auth
            ).status_code,
            422,
        )

        # success path
        with patch.object(main, "analyze_candidate", new=AsyncMock(return_value={"skills": ["C++"]})), \
             patch.object(main, "analyze_jd", new=AsyncMock(return_value={"profile": {}, "plan": {}})):
            r = c.post("/api/jd/analyze", json=base, headers=auth)
        self.assertEqual(r.status_code, 200)

        # candidate extraction failure → falls back, still 200
        with patch.object(main, "analyze_candidate", new=AsyncMock(side_effect=RuntimeError("boom"))), \
             patch.object(main, "analyze_jd", new=AsyncMock(return_value={"profile": {}, "plan": {}})):
            r2 = c.post("/api/jd/analyze", json=base, headers=auth)
        self.assertEqual(r2.status_code, 200)

        # LLM failure → 500 (local keeps the detail for debugging, L33)
        with patch.object(main, "analyze_candidate", new=AsyncMock(return_value=None)), \
             patch.object(main, "analyze_jd", new=AsyncMock(side_effect=RuntimeError("boom"))):
            r3 = c.post("/api/jd/analyze", json=base, headers=auth)
        self.assertEqual(r3.status_code, 500)

    def test_coach_endpoint_generate_and_cache(self):
        import asyncio

        from services.auth import decode_token
        from services.history import save_interview

        class FakeCoach:
            def __init__(self):
                self.calls = 0

            async def generate(self, transcript, report):
                self.calls += 1
                return {
                    "summary": "表现不错",
                    "weak_analysis": ["深度不足"],
                    "study_plan": [{"action": "复习系统设计", "why": "薄弱"}],
                    "next_focus": ["系统设计"],
                    "next_first_question": "讲讲你的系统设计思路",
                }

        c = self.client
        # unauthenticated → 401
        self.assertEqual(c.post("/api/history/x/coach").status_code, 401)

        token = self._register("coach_user")
        auth = {"Authorization": f"Bearer {token}"}
        user_id = decode_token(token)

        async def seed():
            await save_interview(
                "sess_coach", "UE开发", "某公司",
                [{"role": "interviewer", "content": "你好", "phase": "intro"}],
                {"overall_score": 3.0},
                user_id,
                jd={"profile": {"role_title": "UE开发"}},
            )

        asyncio.run(seed())

        # missing record → 404
        fake = FakeCoach()
        with patch.object(main, "coach", fake):
            self.assertEqual(c.post("/api/history/nope/coach", headers=auth).status_code, 404)
            r = c.post("/api/history/sess_coach/coach", headers=auth)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["coach"]["summary"], "表现不错")
            # second call is served from the cache (no extra LLM call)
            r2 = c.post("/api/history/sess_coach/coach", headers=auth)
            self.assertEqual(r2.json()["coach"]["next_first_question"], "讲讲你的系统设计思路")
        self.assertEqual(fake.calls, 1)

        # another user cannot generate for someone else's record
        token_b = self._register("coach_user2")
        with patch.object(main, "coach", FakeCoach()):
            rb = c.post(
                "/api/history/sess_coach/coach",
                headers={"Authorization": f"Bearer {token_b}"},
            )
        self.assertEqual(rb.status_code, 404)

    def test_coach_endpoint_llm_failure_returns_502(self):
        """L4: a coach LLM failure must not surface as a raw 500."""
        import asyncio

        from services.auth import decode_token
        from services.history import save_interview

        class BoomCoach:
            async def generate(self, transcript, report):
                raise RuntimeError("llm boom")

        c = self.client
        token = self._register("coach_boom")
        auth = {"Authorization": f"Bearer {token}"}
        user_id = decode_token(token)

        async def seed():
            await save_interview(
                "sess_coach_boom", "岗位", "公司",
                [{"role": "interviewer", "content": "你好", "phase": "intro"}],
                {"overall_score": 3.0},
                user_id,
            )

        asyncio.run(seed())

        with patch.object(main, "coach", BoomCoach()):
            r = c.post("/api/history/sess_coach_boom/coach", headers=auth)
        self.assertEqual(r.status_code, 502)


if __name__ == "__main__":
    import unittest

    unittest.main()
