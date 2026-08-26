"""Tests for structured output (with_structured_output) and eval helpers."""
import json
import unittest
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

from agent.interviewer import EvaluatorAgent, InterviewerAgent
from evals.eval_interviewer import (
    check_report_completeness,
    judge_followup_relevance,
    measure_score_stability,
)
from models.interview import InterviewState


class ReportCompletenessTest(unittest.TestCase):
    def test_valid_report(self):
        r = {
            "overall_score": 3.5,
            "dimension_scores": {"专业深度": {"score": 4, "comment": "c"}},
            "highlights": ["a"],
            "weak_points": [{"area": "x", "description": "d", "suggestion": "s"}],
            "recommended_topics": ["t"],
            "summary": "总体不错",
        }
        res = check_report_completeness(r)
        self.assertTrue(res["ok"])
        self.assertEqual(res["missing"], [])
        self.assertEqual(res["issues"], [])

    def test_missing_keys_and_bad_values(self):
        r = {"overall_score": 9, "dimension_scores": {"a": {"score": 0}}, "summary": ""}
        res = check_report_completeness(r)
        self.assertFalse(res["ok"])
        self.assertIn("highlights", res["missing"])
        self.assertTrue(any("超出" in i for i in res["issues"]))
        self.assertTrue(any("score 非法" in i for i in res["issues"]))
        self.assertTrue(any("summary 为空" in i for i in res["issues"]))


class FakeRunnable:
    """Offline stand-in for a with_structured_output wrapper."""

    def __init__(self, schema, payload):
        self._schema = schema
        self._payload = payload

    async def ainvoke(self, messages):
        return self._schema(**self._payload)


class FakeStructuredLLM:
    """Offline LLM whose with_structured_output returns a fixed payload."""

    def __init__(self, payload):
        self._payload = payload

    def with_structured_output(self, schema, **kwargs):
        return FakeRunnable(schema, self._payload)


VALID_REPORT = {
    "overall_score": 4.0,
    "dimension_scores": {"沟通表达": {"score": 4, "comment": "清晰"}},
    "highlights": ["回答完整"],
    "weak_points": [],
    "recommended_topics": ["系统设计"],
    "summary": "模拟报告",
}


class StructuredOutputTest(IsolatedAsyncioTestCase):
    def _state(self):
        state = InterviewState(session_id="s", scenario_id="generic", role_title="测试岗")
        state.add_message("interviewer", "你好")
        state.add_message("candidate", "我做过 RAG 项目")
        return state

    async def test_evaluator_structured(self):
        agent = EvaluatorAgent(llm=FakeStructuredLLM(VALID_REPORT))
        report = await agent.evaluate(self._state())
        self.assertEqual(report["overall_score"], 4.0)
        self.assertEqual(report["dimension_scores"]["沟通表达"]["score"], 4)
        self.assertIn("highlights", report)

    async def test_scorer_structured(self):
        agent = InterviewerAgent(llm=FakeStructuredLLM({"score": 2, "weakness_hint": "空泛"}))
        info = await agent._score_last_answer(self._state())
        self.assertEqual(info["score"], 2)
        self.assertEqual(info["weakness_hint"], "空泛")

    async def test_evaluator_falls_back_without_structured(self):
        class PlainLLM:
            async def ainvoke(self, messages):
                return SimpleNamespace(content=json.dumps(VALID_REPORT, ensure_ascii=False))

        agent = EvaluatorAgent(llm=PlainLLM())
        report = await agent.evaluate(self._state())
        self.assertEqual(report["overall_score"], 4.0)

    async def test_judge_relevance_structured(self):
        llm = FakeStructuredLLM({"relevance": 4, "reason": "承接了回答"})
        r = await judge_followup_relevance(llm, "q1", "a1", "q2")
        self.assertEqual(r["relevance"], 4)

    async def test_measure_score_stability(self):
        class ScorerLLM:
            def __init__(self):
                self._n = 0

            async def ainvoke(self, messages):
                prompt = "".join(getattr(m, "content", "") for m in messages)
                if "评分标准" in prompt:
                    self._n += 1
                    return SimpleNamespace(content=json.dumps({"score": 4, "weakness_hint": "稳定"}))
                return SimpleNamespace(content="你好")

        llm = ScorerLLM()
        res = await measure_score_stability(llm, "我的答案", n=3)
        self.assertEqual(len(res["scores"]), 3)
        self.assertEqual(res["max_delta"], 0)


if __name__ == "__main__":
    unittest.main()
