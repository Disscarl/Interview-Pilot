import unittest
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

from agent.interviewer import _limit_transcript, InterviewerAgent
from models.interview import InterviewState


class LimitTranscriptTest(unittest.TestCase):
    def test_short_passthrough(self):
        self.assertEqual(_limit_transcript("你好"), "你好")

    def test_long_is_truncated(self):
        t = "字" * 20000
        r = _limit_transcript(t)
        self.assertLess(len(r), 10000)
        self.assertIn("省略", r)
        self.assertTrue(r.startswith("字" * 10))  # head kept
        self.assertTrue(r.endswith("字" * 10))    # tail kept


class FakeLLM:
    """Offline stand-in for the chat model: distinguishes the scorer prompt
    (contains 评分标准) from the main interviewer prompt."""

    def __init__(self, score_response=None, fail_scoring=False, chunks=("好", "的")):
        self._score = score_response
        self._fail = fail_scoring
        self._chunks = chunks

    async def ainvoke(self, messages):
        if self._fail:
            raise RuntimeError("llm boom")
        prompt_text = "".join(getattr(m, "content", "") for m in messages)
        if "评分标准" in prompt_text:
            return SimpleNamespace(content=self._score or '{"score": 3, "weakness_hint": "空泛"}')
        return SimpleNamespace(content="你好，请介绍一下自己。")

    async def astream(self, messages):
        for c in self._chunks:
            yield SimpleNamespace(content=c)


class ScoringTest(IsolatedAsyncioTestCase):
    def _state(self):
        state = InterviewState(session_id="s1", scenario_id="generic", role_title="测试岗")
        state.add_message("candidate", "我做过 RAG 项目，用 LangChain 搭了检索链路。")
        return state

    async def test_score_last_answer(self):
        agent = InterviewerAgent(FakeLLM(score_response='{"score": 4, "weakness_hint": "细节充分"}'))
        info = await agent._score_last_answer(self._state())
        self.assertEqual(info["score"], 4)
        self.assertIn("细节充分", info["weakness_hint"])

    async def test_score_parses_fences_and_clamps(self):
        agent = InterviewerAgent(FakeLLM(score_response='```json\n{"score": 9, "weakness_hint": "x"}\n```'))
        info = await agent._score_last_answer(self._state())
        self.assertEqual(info["score"], 5)  # clamped to 1..5

    async def test_score_failure_returns_none(self):
        agent = InterviewerAgent(FakeLLM(fail_scoring=True))
        self.assertIsNone(await agent._score_last_answer(self._state()))

    async def test_score_skips_without_answer(self):
        agent = InterviewerAgent(FakeLLM())
        state = InterviewState(session_id="s", scenario_id="g")
        self.assertIsNone(await agent._score_last_answer(state))

    def test_system_prompt_includes_score_guidance(self):
        agent = InterviewerAgent(FakeLLM())
        state = self._state()
        with_score = agent._build_system_prompt(state, {"score": 2, "weakness_hint": "空泛"})
        self.assertIn("质量评分：2/5", with_score)
        self.assertIn("适当降低难度", with_score)
        without = agent._build_system_prompt(state)
        self.assertNotIn("回答质量评估", without)

    async def test_generate_stream_with_scoring(self):
        agent = InterviewerAgent(FakeLLM())
        state = self._state()
        tokens = [t async for t in agent.generate_next_stream(state)]
        self.assertEqual("".join(tokens), "好的")
        self.assertEqual(state.messages[-1]["role"], "interviewer")


if __name__ == "__main__":
    unittest.main()
