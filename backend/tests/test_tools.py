"""Tests for the interviewer's function-calling loop (agent/tools.py)."""
import unittest
from unittest import IsolatedAsyncioTestCase

from langchain_core.messages import AIMessageChunk, ToolMessage

from agent.interviewer import InterviewerAgent
from agent.tools import build_interview_tools
from models.interview import InterviewState


def _state_with_resume():
    state = InterviewState(session_id="s", scenario_id="generic", role_title="测试岗")
    state.candidate_profile = {
        "name": "张三",
        "skills": ["C++", "UE5"],
        "projects": ["数字人对话系统", "UE 战斗系统"],
        "work_history": ["某游戏公司 UE 客户端开发 3 年"],
        "years_of_experience": "3年",
    }
    state.jd_profile = {
        "company_name": "某公司",
        "company_research": {"business": "游戏研发", "products": ["开放世界游戏"]},
    }
    state.add_message("candidate", "我做过 UE 项目")
    return state


class BuildToolsTest(unittest.TestCase):
    def test_tools_bound_to_session_data(self):
        tools = build_interview_tools(_state_with_resume())
        names = {t.name for t in tools}
        self.assertEqual(names, {"search_candidate_info", "query_company_info"})

    def test_search_candidate_info_hits_fragments(self):
        tools = build_interview_tools(_state_with_resume())
        search = next(t for t in tools if t.name == "search_candidate_info")
        result = search.invoke({"query": "UE"})
        self.assertIn("UE", result)
        self.assertIn("项目", result)

    def test_search_miss_reports_gracefully(self):
        tools = build_interview_tools(_state_with_resume())
        search = next(t for t in tools if t.name == "search_candidate_info")
        self.assertIn("未找到", search.invoke({"query": "区块链"}))

    def test_query_company_info(self):
        tools = build_interview_tools(_state_with_resume())
        company = next(t for t in tools if t.name == "query_company_info")
        result = company.invoke({})
        self.assertIn("游戏研发", result)

    def test_no_data_returns_no_tools(self):
        state = InterviewState(session_id="s", scenario_id="generic")
        self.assertEqual(build_interview_tools(state), [])


class FakeToolLLM:
    """Offline LLM: round 1 issues a tool call, round 2 streams content."""

    def __init__(self, tool_chunk, content=("你", "好，", "请介绍一下", "自己。")):
        self._tool_chunk = tool_chunk
        self._content = content
        self.calls: list[list] = []

    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        self.calls.append(list(messages))
        if len(self.calls) == 1:
            yield self._tool_chunk
        else:
            for c in self._content:
                yield AIMessageChunk(content=c)


def _tool_chunk(name: str, args: str, call_id: str):
    return AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": name, "args": args, "id": call_id, "index": 0}],
    )


class ToolLoopTest(IsolatedAsyncioTestCase):
    async def test_tool_loop_executes_and_streams(self):
        fake = FakeToolLLM(_tool_chunk("search_candidate_info", '{"query": "UE"}', "call_1"))
        agent = InterviewerAgent(llm=fake)
        state = _state_with_resume()
        tokens = [t async for t in agent.stream_next(state, None, tools=build_interview_tools(state))]

        self.assertEqual("".join(tokens), "你好，请介绍一下自己。")
        self.assertEqual(len(fake.calls), 2)  # tool round + content round

        tool_msgs = [m for m in fake.calls[1] if isinstance(m, ToolMessage)]
        self.assertEqual(len(tool_msgs), 1)
        self.assertIn("UE", tool_msgs[0].content)  # grounded in real resume data
        self.assertEqual(state.messages[-1]["content"], "你好，请介绍一下自己。")

    async def test_no_tool_call_single_round(self):
        fake = FakeToolLLM(AIMessageChunk(content="直接回答"))
        agent = InterviewerAgent(llm=fake)
        state = _state_with_resume()
        tokens = [t async for t in agent.stream_next(state, None, tools=build_interview_tools(state))]
        self.assertEqual("".join(tokens), "直接回答")
        self.assertEqual(len(fake.calls), 1)

    async def test_unknown_tool_reports_gracefully(self):
        fake = FakeToolLLM(_tool_chunk("nope_tool", "{}", "call_9"))
        agent = InterviewerAgent(llm=fake)
        state = _state_with_resume()
        tokens = [t async for t in agent.stream_next(state, None, tools=build_interview_tools(state))]
        self.assertEqual("".join(tokens), "你好，请介绍一下自己。")
        tool_msgs = [m for m in fake.calls[1] if isinstance(m, ToolMessage)]
        self.assertIn("未知工具", tool_msgs[0].content)


if __name__ == "__main__":
    unittest.main()
