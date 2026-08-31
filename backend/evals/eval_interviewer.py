"""LLM-as-judge evaluation for the interviewer agent.

Runs three checks against a real LLM (or an injected fake in tests):
1. report field completeness  — pure function, no LLM
2. follow-up question relevance — LLM judge scores 1-5
3. answer-score stability — repeat the scorer on the same answer, check spread

Usage (from backend/):
    python evals/eval_interviewer.py
"""
import asyncio
import json
import os
import statistics
import sys

# Allow running as `python evals/eval_interviewer.py` from the repo root too.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import BaseModel, Field  # noqa: E402

from agent.interviewer import EvaluatorAgent, InterviewerAgent  # noqa: E402
from models.interview import InterviewState  # noqa: E402
from services.llm import get_default_llm  # noqa: E402

REQUIRED_REPORT_KEYS = [
    "overall_score", "dimension_scores", "highlights",
    "weak_points", "recommended_topics", "summary",
]


def check_report_completeness(report: dict) -> dict:
    """Validate a generated evaluation report (pure, no LLM)."""
    missing = [k for k in REQUIRED_REPORT_KEYS if k not in report]
    issues: list[str] = []
    if "overall_score" in report:
        s = report.get("overall_score")
        if not (isinstance(s, (int, float)) and 0 <= s <= 5):
            issues.append(f"overall_score 超出 0-5: {s!r}")
    dims = report.get("dimension_scores") or {}
    if not dims:
        issues.append("dimension_scores 为空")
    for name, dim in dims.items():
        score = dim.get("score") if isinstance(dim, dict) else None
        if not (isinstance(score, int) and 1 <= score <= 5):
            issues.append(f"维度 {name} score 非法: {score!r}")
    if not (report.get("summary") or "").strip():
        issues.append("summary 为空")
    return {"ok": not missing and not issues, "missing": missing, "issues": issues}


# ─── Follow-up relevance judge ─────────────────────────────

_JUDGE_SYSTEM = """你是面试评估员。判断面试官的下一个追问是否与候选人上一轮的回答相关：
1 = 完全无关（自说自话）
2 = 勉强相关
3 = 一般相关，但没接住回答要点
4 = 相关，且承接了回答内容
5 = 高度相关，针对回答细节深挖

只输出 JSON：{{"relevance": 整数1-5, "reason": "一句话理由"}}"""


class RelevanceJudge(BaseModel):
    relevance: int = Field(ge=1, le=5)
    reason: str = Field(default="")


def _judge_messages(prev_q: str, answer: str, next_q: str) -> list:
    from langchain_core.messages import HumanMessage, SystemMessage
    return [
        SystemMessage(content=_JUDGE_SYSTEM),
        HumanMessage(
            content=f"前一个问题：{prev_q}\n\n候选人回答：{answer}\n\n面试官追问：{next_q}"
        ),
    ]


async def judge_followup_relevance(llm, prev_q: str, answer: str, next_q: str) -> dict:
    """Score (1-5) how well the follow-up question builds on the answer."""
    messages = _judge_messages(prev_q, answer, next_q)
    try:
        judge = llm.with_structured_output(RelevanceJudge, method="function_calling")
        res = await judge.ainvoke(messages)
        return {"relevance": int(res.relevance), "reason": res.reason}
    except Exception:
        # fallback: plain JSON parse
        resp = await llm.ainvoke(messages)
        content = str(resp.content or "")
        if "```" in content:
            parts = content.split("```")
            content = parts[1] if len(parts) >= 2 else content
        try:
            data = json.loads(content.strip())
            return {"relevance": int(data.get("relevance", 3)), "reason": str(data.get("reason", ""))}
        except Exception:
            # L3: a failed judge must not score 0 and drag the average down;
            # the caller filters these out and tracks the failure ratio.
            return None


async def measure_score_stability(llm, answer: str, n: int = 3) -> dict:
    """Run the interviewer's answer scorer n times; report the spread."""
    agent = InterviewerAgent(llm=llm)
    state = InterviewState(session_id="eval", scenario_id="generic", role_title="测试岗")
    state.add_message("candidate", answer)
    scores = []
    for _ in range(n):
        info = await agent._score_last_answer(state)
        scores.append(info["score"] if info else None)
    valid = [s for s in scores if s is not None]
    return {
        "scores": scores,
        # None when there is no valid sample — a fully-failed scorer must not
        # report a stable 0-delta and pass the eval (L2).
        "max_delta": (max(valid) - min(valid)) if len(valid) >= 2 else None,
        "std": round(statistics.pstdev(valid), 2) if len(valid) >= 2 else 0.0,
        "valid_count": len(valid),
    }


# ─── Samples & runner ──────────────────────────────────────

SAMPLES = [
    {
        "prev_q": "请介绍一下你自己和你的技术背景。",
        "answer": "我做了三年 UE 游戏客户端开发，主要负责战斗系统和技能框架，最近在自学 LLM 应用开发。",
        "next_q": "你说在做 LLM 应用，能具体讲讲你做过的一个 Agent 项目吗？",
    },
    {
        "prev_q": "你了解 LangChain 吗？",
        "answer": "用过一些，主要是 Chain 和 Prompt 模板，还没有深入接触过 Agent 编排。",
        "next_q": "那如果让你设计一个多步骤的 Agent 流程，你会怎么考虑状态管理？",
    },
    {
        "prev_q": "讲讲你简历里最有挑战的一个项目。",
        "answer": "做过一个数字人对话系统，难点在控制延迟和对话质量，最后用流式输出解决了一部分。",
        "next_q": "延迟优化你具体做了哪些取舍？",
    },
]


async def run_eval(llm=None) -> dict:
    """Run all checks; returns an aggregate metrics dict."""
    llm = llm or get_default_llm()

    # 1) follow-up relevance over samples (failed judges are filtered out and
    # counted — L3)
    relevance = []
    judge_failures = 0
    for s in SAMPLES:
        r = await judge_followup_relevance(llm, s["prev_q"], s["answer"], s["next_q"])
        if r is None:
            judge_failures += 1
        else:
            relevance.append(r["relevance"])
    judge_failed = judge_failures > len(SAMPLES) / 3

    # 2) score stability on one representative answer
    stability = await measure_score_stability(
        llm, SAMPLES[0]["answer"], n=3
    )

    # 3) full-report completeness via the evaluator
    state = InterviewState(session_id="eval_full", scenario_id="generic", role_title="测试岗")
    for s in SAMPLES[:2]:
        state.add_message("interviewer", s["prev_q"])
        state.add_message("candidate", s["answer"])
    report = await EvaluatorAgent(llm=llm).evaluate(state)
    completeness = check_report_completeness(report)

    return {
        "followup_relevance": {
            "avg": round(sum(relevance) / len(relevance), 2) if relevance else 0,
            "scores": relevance,
            "failed": judge_failures,
            "judge_failed": judge_failed,
        },
        "score_stability": stability,
        "report_completeness": completeness,
        "report_preview": {k: report.get(k) for k in ("overall_score", "summary")},
    }


def main() -> None:
    metrics = asyncio.run(run_eval())
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    max_delta = metrics["score_stability"]["max_delta"]
    ok = (
        metrics["report_completeness"]["ok"]
        and metrics["followup_relevance"]["avg"] >= 3
        and not metrics["followup_relevance"]["judge_failed"]
        # None → the scorer produced no valid samples → must not pass (L2).
        and max_delta is not None
        and max_delta <= 1
    )
    print("\n== eval 结论:", "PASS ✅" if ok else "NEEDS ATTENTION ⚠️")


if __name__ == "__main__":
    main()
