import unittest
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

from langchain_core.messages import HumanMessage

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

    def test_output_within_budget_including_marker(self):
        # L23: the omission marker must count against the budget.
        t = "字" * 20000
        r = _limit_transcript(t, max_chars=8000)
        self.assertLessEqual(len(r), 8000)

    def test_tiny_budget_keeps_head_only(self):
        # L23: degenerate budget (< head) falls back to head-only truncation.
        t = "字" * 20000
        r = _limit_transcript(t, max_chars=100)
        self.assertLessEqual(len(r), 100)
        self.assertNotIn("省略", r)


class ClosingDetectionTest(unittest.TestCase):
    def test_closing_markers_detected(self):
        self.assertTrue(_looks_like_closing("今天的面试就到这里，感谢你的参与。"))
        self.assertTrue(_looks_like_closing("感谢你参加本次面试，再见！"))
        self.assertTrue(_looks_like_closing("面试到此结束，期待你的好消息。"))
        self.assertTrue(_looks_like_closing("祝你好运，保持联系。"))

    def test_opening_phrases_are_not_closing(self):
        # 开场白与收尾语词汇重叠 —— 这些绝不能算收尾。
        self.assertFalse(_looks_like_closing("欢迎参加今天的面试，我是本次面试的面试官。"))
        self.assertFalse(_looks_like_closing("感谢你参加本次面试，我们开始吧。"))
        self.assertFalse(_looks_like_closing("本次面试我们将分几个环节进行。"))
        self.assertFalse(_looks_like_closing("谢谢你的参与，我们先做个自我介绍吧。"))
        self.assertFalse(_looks_like_closing("期待你的加入，请先介绍一下自己。"))

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

    async def test_score_tolerates_non_integer(self):
        # L6: a "3.5"-style score must not crash the scoring turn.
        agent = InterviewerAgent(FakeLLM(score_response='{"score": "3.5", "weakness_hint": "x"}'))
        info = await agent._score_last_answer(self._state())
        self.assertEqual(info["score"], 3)

    def test_system_prompt_has_injection_boundary(self):
        # L5: prompts declare that user-supplied data is untrusted input.
        agent = InterviewerAgent(FakeLLM())
        sp = agent._build_system_prompt(self._state())
        self.assertIn("不可信的外部输入", sp)

    def test_scorer_prompt_delimiters_answer(self):
        # L5: the candidate answer is wrapped in an explicit delimiter.
        from agent.prompts import ANSWER_SCORER_PROMPT
        messages = ANSWER_SCORER_PROMPT.format_messages(role="测试岗", answer="我的回答")
        human = messages[-1].content
        self.assertIn("<CANDIDATE_ANSWER>", human)
        self.assertIn("</CANDIDATE_ANSWER>", human)

    def test_build_history_no_duplicate_latest_answer(self):
        # L7: the latest candidate answer is excluded from the recent-history
        # window here (the caller appends it once as the current-prompt input),
        # so it must not appear twice.
        agent = InterviewerAgent(FakeLLM())
        state = InterviewState(session_id="s1", scenario_id="generic", role_title="测试岗")
        state.add_message("interviewer", "你好")
        state.add_message("candidate", "我有五年经验")
        state.add_message("interviewer", "具体讲讲")
        state.add_message("candidate", "做过电商系统")
        history = agent._build_history(state)
        human_contents = [m.content for m in history if isinstance(m, HumanMessage)]
        self.assertNotIn("做过电商系统", human_contents)
        self.assertIn("我有五年经验", human_contents)

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
        # 已有一轮问答（收尾检测只在开场之后生效）
        state.add_message("interviewer", "你刚才提到了 RAG 项目，能具体讲讲检索链路吗？")
        state.add_message("candidate", "好的，我们用的是 LangChain……")
        tokens = [t async for t in agent.stream_next(state)]
        self.assertTrue("".join(tokens))
        self.assertEqual(state.phase, InterviewPhase.CLOSING)
        self.assertEqual(state.messages[-1]["phase"], "closing")

    async def test_opening_line_never_triggers_closing(self):
        # 回归用例：面试官第一句话（"欢迎参加今天的面试…"）绝不能跳到收尾。
        agent = InterviewerAgent(FakeLLM(chunks=("欢迎参加今天的面试，", "请先做个自我介绍吧。")))
        state = InterviewState(session_id="s1", scenario_id="generic", role_title="测试岗")
        tokens = [t async for t in agent.stream_next(state)]
        self.assertEqual("".join(tokens), "欢迎参加今天的面试，请先做个自我介绍吧。")
        self.assertEqual(state.phase, InterviewPhase.INTRO)
        self.assertEqual(state.messages[-1]["phase"], "intro")

    async def test_opening_line_with_closing_words_still_safe(self):
        # 即使开场第一句就含结束语（模型异常输出），也保持 INTRO 不跳阶段。
        agent = InterviewerAgent(FakeLLM(chunks=("面试就到这里，", "感谢参与。")))
        state = InterviewState(session_id="s1", scenario_id="generic", role_title="测试岗")
        tokens = [t async for t in agent.stream_next(state)]
        self.assertEqual(state.phase, InterviewPhase.INTRO)
        self.assertEqual(state.messages[-1]["phase"], "intro")

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
