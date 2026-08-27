"""Tests for the LangGraph interview step (agent/graph.py)."""
import json
import unittest
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

from agent.graph import build_interview_step_graph
from agent.interviewer import EvaluatorAgent, InterviewerAgent
from models.interview import InterviewPhase, InterviewState


class FakeLLM:
    """Offline LLM: scores (scorer prompt), evaluates (report json), streams."""

    def __init__(self, chunks=("你", "好，", "请介绍一下", "自己。"), report=None):
        self._chunks = chunks
        self._report = report or {
            "overall_score": 4.0,
            "summary": "模拟报告",
            "dimension_scores": {"沟通表达": {"score": 4, "comment": "清晰"}},
            "highlights": ["回答完整"],
            "weak_points": [],
            "recommended_topics": ["系统设计"],
        }

    async def ainvoke(self, messages):
        prompt = "".join(getattr(m, "content", "") for m in messages)
        if "评估维度" in prompt:  # evaluator prompt → full report json
            return SimpleNamespace(content=json.dumps(self._report, ensure_ascii=False))
        # otherwise it's the answer-scorer prompt → score json
        return SimpleNamespace(content=json.dumps({"score": 3, "weakness_hint": "空泛"}))

    async def astream(self, messages):
        for c in self._chunks:
            yield SimpleNamespace(content=c)


class FakeWS:
    def __init__(self):
        self.sent = []

    async def send_text(self, text: str):
        self.sent.append(json.loads(text))


class GraphStepTest(IsolatedAsyncioTestCase):
    def setUp(self):
        llm = FakeLLM()
        self.interviewer = InterviewerAgent(llm=llm)
        self.evaluator = EvaluatorAgent(llm=llm)
        self.ws = FakeWS()
        self.saved = []

        async def fake_save(st, rep):
            self.saved.append((st.session_id, rep))

        self.graph = build_interview_step_graph(
            self.interviewer,
            self.evaluator,
            ws=self.ws,
            save_history=fake_save,
        )

    def _state(self):
        return InterviewState(session_id="s1", scenario_id="generic", role_title="测试岗")

    async def test_first_question_generates(self):
        state = self._state()
        result = await self.graph.ainvoke({"interview": state})
        types = [m["type"] for m in self.ws.sent]
        self.assertEqual(types[0], "thinking")
        self.assertTrue(any(t == "stream_token" for t in types))
        self.assertEqual(types[-1], "stream_end")
        self.assertFalse(result.get("ended"))
        self.assertEqual(state.messages[-1]["role"], "interviewer")
        self.assertEqual(self.saved, [])  # not ended → no history write

    async def test_answer_generates_next(self):
        state = self._state()
        state.add_message("candidate", "我有三年 UE 开发经验")
        result = await self.graph.ainvoke({"interview": state})
        self.assertFalse(result.get("ended"))
        self.assertEqual(self.ws.sent[-1]["type"], "stream_end")

    async def test_force_evaluate_ends_and_saves(self):
        state = self._state()
        state.add_message("candidate", "回答内容")
        result = await self.graph.ainvoke({
            "interview": state,
            "force_evaluate": True,
            "end_content": "面试已结束，正在生成评估报告...",
        })
        self.assertTrue(result.get("ended"))
        types = [m["type"] for m in self.ws.sent]
        self.assertIn("interview_end", types)
        self.assertEqual(self.ws.sent[-1]["type"], "report")
        self.assertEqual(self.ws.sent[-1]["report"]["overall_score"], 4.0)
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0][0], "s1")

    async def test_closing_auto_evaluates(self):
        state = self._state()
        state.phase = InterviewPhase.CLOSING
        state.add_message("interviewer", "面试接近尾声，你有什么问题吗？")
        state.add_message("candidate", "没有了，谢谢。")
        result = await self.graph.ainvoke({"interview": state})
        self.assertTrue(result.get("ended"))
        self.assertIn("report", [m["type"] for m in self.ws.sent])


if __name__ == "__main__":
    unittest.main()
