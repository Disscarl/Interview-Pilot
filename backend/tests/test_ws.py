"""WebSocket-layer tests: create/stream/answer/end/report, resume, ownership.

The interviewer/evaluator LLM is replaced with an offline fake, so no real
DeepSeek/讯飞 calls happen. DB/audio/tts paths are patched to a temp dir.
"""
import json
import os
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

os.environ.setdefault("DEEPSEEK_API_KEY", "dummy-for-tests")
os.environ.setdefault("JWT_SECRET", "test-secret-for-unittest")

import main  # noqa: E402
from agent.interviewer import InterviewerAgent, EvaluatorAgent  # noqa: E402
from services.ratelimit import rate_limiter  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402


class FakeLLM:
    """Minimal offline stand-in for a LangChain chat model."""

    def __init__(self, chunks=("你", "好，", "请介绍一下", "自己。"), report=None):
        self._chunks = chunks
        self._report = report or {
            "overall_score": 4.0,
            "summary": "模拟评估通过",
            "dimension_scores": {"沟通表达": {"score": 4, "comment": "清晰有条理"}},
            "highlights": ["回答完整"],
            "weak_points": [{"area": "深度", "description": "略浅", "suggestion": "多讲细节"}],
            "recommended_topics": ["分布式系统"],
        }

    async def astream(self, messages):
        for c in self._chunks:
            yield SimpleNamespace(content=c)

    async def ainvoke(self, messages):
        return SimpleNamespace(content=json.dumps(self._report, ensure_ascii=False))


def _drain(ws, stop_types):
    """Receive WS messages until one of `stop_types` arrives; return all."""
    got = []
    while True:
        m = ws.receive_json()
        got.append(m)
        if m["type"] in stop_types:
            return got


class WsTest(TestCase):
    def setUp(self):
        rate_limiter._hits.clear()
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
        self.client = self.enterContext(TestClient(main.app))
        llm = FakeLLM()
        self.enterContext(patch.object(main, "interviewer", InterviewerAgent(llm)))
        self.enterContext(patch.object(main, "evaluator", EvaluatorAgent(llm)))

    def _register(self, name: str) -> str:
        r = self.client.post(
            "/api/auth/register", json={"username": name, "password": "pw1234"}
        )
        self.assertEqual(r.status_code, 200)
        return r.json()["token"]

    def test_create_stream_answer_end_report(self):
        token = self._register("alice")
        sid = "sess_e2e_1"
        with self.client.websocket_connect(f"/ws/{sid}?token={token}") as ws:
            ws.send_json({"action": "create", "jd": {"profile": {"role_title": "测试工程师"}}})
            got = _drain(ws, {"stream_end"})
            self.assertEqual(got[0]["type"], "created")
            self.assertIn("thinking", [m["type"] for m in got])
            self.assertTrue(any(m["type"] == "stream_token" for m in got))
            self.assertEqual(got[-1]["type"], "stream_end")

            ws.send_json({"action": "answer", "content": "我有五年测试经验"})
            got2 = _drain(ws, {"stream_end"})
            self.assertEqual(got2[-1]["type"], "stream_end")

            ws.send_json({"action": "end"})
            got3 = _drain(ws, {"report"})
            self.assertIn("interview_end", [m["type"] for m in got3])
            self.assertEqual(got3[-1]["report"]["overall_score"], 4.0)

        # History persisted for the owning user.
        r = self.client.get("/api/history", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(sid, [it["id"] for it in r.json()["interviews"]])

    def test_resume_replays_history(self):
        token = self._register("bob")
        sid = "sess_resume_1"
        with self.client.websocket_connect(f"/ws/{sid}?token={token}") as ws:
            ws.send_json({"action": "create", "jd": {"profile": {"role_title": "后端工程师"}}})
            _drain(ws, {"stream_end"})
        # Reconnect with resume → the session is replayed, not restarted.
        with self.client.websocket_connect(f"/ws/{sid}?token={token}") as ws:
            ws.send_json({"action": "create", "jd": {"profile": {"role_title": "后端工程师"}}, "resume": True})
            m = ws.receive_json()
            self.assertEqual(m["type"], "resume")
            self.assertGreaterEqual(len(m["messages"]), 1)

    def test_cross_user_hijack_rejected(self):
        token_a = self._register("carol")
        token_b = self._register("dave")
        sid = "sess_hijack_1"
        with self.client.websocket_connect(f"/ws/{sid}?token={token_a}") as ws:
            ws.send_json({"action": "create", "jd": {"profile": {"role_title": "测试"}}})
            _drain(ws, {"stream_end"})
        # User B must NOT be able to take over A's live session.
        with self.client.websocket_connect(f"/ws/{sid}?token={token_b}") as ws:
            ws.send_json({"action": "create", "jd": {"profile": {"role_title": "测试"}}})
            m = ws.receive_json()
            self.assertEqual(m["type"], "error")
            self.assertIn("不属于当前用户", m["content"])

    def test_malformed_json_gets_error_not_disconnect(self):
        token = self._register("erin")
        sid = "sess_badjson_1"
        with self.client.websocket_connect(f"/ws/{sid}?token={token}") as ws:
            ws.send_json({"action": "create", "jd": {"profile": {"role_title": "测试"}}})
            _drain(ws, {"stream_end"})
            ws.send_text("not json at all")
            m = ws.receive_json()
            self.assertEqual(m["type"], "error")
            # Connection stays alive → a valid answer still gets a stream.
            ws.send_json({"action": "answer", "content": "继续"})
            got = _drain(ws, {"stream_end"})
            self.assertEqual(got[-1]["type"], "stream_end")


if __name__ == "__main__":
    import unittest

    unittest.main()
