"""LangGraph interview step — explicit Agent orchestration.

Per-turn invocation: the WebSocket handler calls
``await step_graph.ainvoke({"interview": state})`` once for the opening
question and once per candidate answer. The graph scores the answer,
routes by phase/question count (or a forced evaluate), streams the next
question, and can finish the interview by evaluating + persisting history.

WS message protocol is unchanged
(thinking / stream_token / stream_end / interview_end / report).
"""
import json
import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from models.interview import InterviewPhase
from agent.tools import build_interview_tools

logger = logging.getLogger("interview-pilot")

FALLBACK_REPORT = {
    "overall_score": 0,
    "summary": "评估生成失败，请查看对话记录。",
    "dimension_scores": {},
    "highlights": [],
    "weak_points": [],
    "recommended_topics": [],
}


class InterviewStepState(TypedDict):
    interview: Any            # models.interview.InterviewState (mutated by nodes)
    score_info: dict | None   # answer-quality score for the last answer
    force_evaluate: bool      # user clicked 结束
    end_content: str          # text shown in the interview_end message
    ended: bool               # True once the interview finished


def build_interview_step_graph(interviewer, evaluator, ws, save_history):
    """Build a compiled per-turn LangGraph step.

    - interviewer: agent.interviewer.InterviewerAgent
    - evaluator:   agent.interviewer.EvaluatorAgent
    - ws:          FastAPI WebSocket (streams tokens / report)
    - save_history: async (state, report) -> None
    """

    async def score_answer_node(state: InterviewStepState) -> dict:
        info = await interviewer._score_last_answer(state["interview"])
        return {"score_info": info}

    def route_node(state: InterviewStepState) -> str:
        interview = state["interview"]
        if state.get("force_evaluate") or (
            interview.phase == InterviewPhase.CLOSING
            and interviewer.should_transition(interview)
        ):
            return "evaluate"
        return "generate"

    async def generate_node(state: InterviewStepState) -> dict:
        interview = state["interview"]
        score_info = state.get("score_info")
        tools = build_interview_tools(interview)
        await ws.send_text(json.dumps({"type": "thinking", "content": True}))
        async for token in interviewer.stream_next(interview, score_info, tools=tools):
            await ws.send_text(json.dumps({"type": "stream_token", "content": token}))
        await ws.send_text(json.dumps({"type": "stream_end", "phase": interview.phase.value}))
        return {"ended": False}

    async def evaluate_node(state: InterviewStepState) -> dict:
        interview = state["interview"]
        interview.phase = InterviewPhase.EVALUATE
        await ws.send_text(json.dumps({
            "type": "interview_end",
            "content": state.get("end_content") or "面试结束，正在生成评估报告...",
        }))
        report = None
        try:
            report = await evaluator.evaluate(interview)
        except Exception as e:
            logger.error("Evaluation failed: %s", e, exc_info=True)
        await save_history(interview, report)
        await ws.send_text(json.dumps({
            "type": "report",
            "report": report or FALLBACK_REPORT,
        }))
        return {"ended": True}

    graph = StateGraph(InterviewStepState)
    graph.add_node("score_answer", score_answer_node)
    graph.add_node("generate_question", generate_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_edge(START, "score_answer")
    graph.add_conditional_edges(
        "score_answer",
        route_node,
        {"generate": "generate_question", "evaluate": "evaluate"},
    )
    graph.add_edge("generate_question", END)
    graph.add_edge("evaluate", END)
    return graph.compile()
