import unittest
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

from agent.interviewer import _limit_transcript, _looks_like_closing, InterviewerAgent
from models.interview import InterviewPhase, InterviewState


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


class ClosingDetectionTest(unittest.TestCase):
    def test_closing_markers_detected(self):
        self.assertTrue(_looks_like_closing("今天的面试就到这里，感谢你的参与。"))
        self.assertTrue(_looks_like_closing("感谢你参加本次面试，再见！"))
        self.assertTrue(_looks_like_closing("面试到此结束，期待你的好消息。"))
        self.assertTrue(_looks_like_closing("祝你好运，保持联系。"))

    def test_non_closing_messages_not_detected(self):
        self.assertFalse(_looks_like_closing("你能具体说说这个项目的难点吗？"))
        self.assertFalse(_looks_like_closing("介绍一下你负责的模块。"))
        self.assertFalse(_looks_like_closing(""))
        self.assertFalse(_looks_like_closing("我看看你的简历，稍等。"))


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

    async def test_closing_message_advances_phase(self):
        agent = InterviewerAgent(FakeLLM(chunks=("今天的面试就到这里，感谢你的参与，", "期待你的好消息。")))
        state = InterviewState(session_id="s1", scenario_id="generic", role_title="测试岗")
        state.phase = InterviewPhase.TECH_2
        tokens = [t async for t in agent.stream_next(state)]
        self.assertTrue("".join(tokens))
        self.assertEqual(state.phase, InterviewPhase.CLOSING)
        self.assertEqual(state.messages[-1]["phase"], "closing")

    async def test_normal_message_keeps_phase(self):
        agent = InterviewerAgent(FakeLLM(chunks=("能具体说说", "这个项目吗？")))
        state = InterviewState(session_id="s1", scenario_id="generic", role_title="测试岗")
        state.phase = InterviewPhase.TECH_2
        tokens = [t async for t in agent.stream_next(state)]
        self.assertEqual("".join(tokens), "能具体说说这个项目吗？")
        self.assertEqual(state.phase, InterviewPhase.TECH_2)
        self.assertEqual(state.messages[-1]["phase"], "tech_2")


if __name__ == "__main__":
    unittest.main()
