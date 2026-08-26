"""Core Interviewer (LLM chain) — manages the interview flow and generates questions."""
import json
import logging
from typing import AsyncGenerator
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from models.interview import InterviewState, InterviewPhase
from models.schemas import AnswerScore, EvaluationReport
from services.llm import get_default_llm
from agent.prompts import SYSTEM_PROMPT

logger = logging.getLogger("interview-pilot")

# Phase descriptions and max questions
PHASE_CONFIG = {
    InterviewPhase.INTRO: {
        "description": "自我介绍和暖场。简短介绍自己，确认候选人的目标岗位与方向，让候选人做自我介绍。",
        "max_questions": 2,
    },
    InterviewPhase.WARM_UP: {
        "description": "暖场题。问一些基础但开放的问题，了解候选人对目标岗位/行业的整体认知水平，建立信心。",
        "max_questions": 3,
    },
    InterviewPhase.TECH_1: {
        "description": "专业基础考查。考查目标岗位核心专业知识与技能的掌握程度，中等难度。",
        "max_questions": 5,
    },
    InterviewPhase.TECH_2: {
        "description": "项目/经历深挖 + 自适应追问。根据候选人前面的回答表现，动态选择追问方向。这是面试的核心阶段。",
        "max_questions": 6,
    },
    InterviewPhase.TECH_3: {
        "description": "综合/开放题。考查结构化思维、行业视野与复杂问题解决能力，高难度。",
        "max_questions": 2,
    },
    InterviewPhase.CLOSING: {
        "description": "收尾。告知面试即将结束，给候选人提问的机会，给出积极的结束语。",
        "max_questions": 1,
    },
}

PHASE_ORDER = [
    InterviewPhase.INTRO,
    InterviewPhase.WARM_UP,
    InterviewPhase.TECH_1,
    InterviewPhase.TECH_2,
    InterviewPhase.TECH_3,
    InterviewPhase.CLOSING,
]

_MAX_TRANSCRIPT_CHARS = 8000
_MAX_TRANSCRIPT_HEAD = 2000


def _limit_transcript(transcript: str, max_chars: int = _MAX_TRANSCRIPT_CHARS) -> str:
    """Keep the head (opening context) and tail (recent Q&A) within a char budget."""
    if len(transcript) <= max_chars:
        return transcript
    head = transcript[:_MAX_TRANSCRIPT_HEAD]
    tail = transcript[-(max_chars - _MAX_TRANSCRIPT_HEAD):]
    return head + "\n\n……（中间对话已省略）……\n\n" + tail


class InterviewerAgent:
    """The core interviewer agent that drives the interview conversation."""

    def __init__(self, llm=None):
        self.llm = llm or get_default_llm()
        self._structured_scorer = None  # lazily-built structured-output wrapper (or False)

    def _scorer_runnable(self):
        """Return a `with_structured_output` scorer wrapper, or None if unsupported."""
        if self._structured_scorer is None:
            try:
                self._structured_scorer = self.llm.with_structured_output(
                    AnswerScore, method="function_calling"
                )
            except Exception as e:
                logger.warning("Structured scoring unavailable, using fallback parsing: %s", e)
                self._structured_scorer = False
        return self._structured_scorer or None

    def _get_phase_config(self, phase: InterviewPhase) -> dict:
        return PHASE_CONFIG.get(phase, PHASE_CONFIG[InterviewPhase.INTRO])

    def _next_phase(self, current: InterviewPhase) -> InterviewPhase:
        """Get the next phase in the interview."""
        try:
            idx = PHASE_ORDER.index(current)
            return PHASE_ORDER[idx + 1]
        except (ValueError, IndexError):
            return InterviewPhase.EVALUATE

    def _count_phase_questions(self, state: InterviewState, phase: InterviewPhase) -> int:
        """Count how many questions were asked in a given phase."""
        return sum(1 for msg in state.messages
                   if msg.get("phase") == phase.value and msg["role"] == "interviewer")

    def should_transition(self, state: InterviewState) -> bool:
        """Determine if we should move to the next phase."""
        current = state.phase
        config = self._get_phase_config(current)
        count = self._count_phase_questions(state, current)
        return count >= config["max_questions"]

    def _build_jd_context(self, state: InterviewState) -> str:
        """Render the JD profile + custom interview plan as a readable text block."""
        p = state.jd_profile or {}
        plan = state.jd_plan or {}
        lines = []
        if p.get("company_name"):
            comp = p["company_name"]
            if p.get("company_type"):
                comp += f"（{p['company_type']}）"
            lines.append(f"公司：{comp}")
        if p.get("industry"):
            lines.append(f"行业：{p['industry']}")
        if p.get("company_products"):
            lines.append("公司主营产品/项目：" + "、".join(p["company_products"]))
        if p.get("role_title"):
            lines.append(f"岗位：{p['role_title']}")
        if p.get("responsibilities"):
            lines.append("岗位职责：" + "；".join(p["responsibilities"]))
        if p.get("requirements"):
            lines.append("任职要求：" + "；".join(p["requirements"]))
        if p.get("tech_stack"):
            lines.append("技术栈：" + "、".join(p["tech_stack"]))
        research = p.get("company_research") or {}
        if research.get("business"):
            lines.append("公司核心业务：" + research["business"])
        if research.get("products"):
            lines.append("公司代表产品/业务线：" + "、".join(research["products"]))
        if research.get("history_projects"):
            lines.append("公司历史项目/里程碑：" + "、".join(research["history_projects"]))
        if research.get("market_position"):
            lines.append("行业地位：" + research["market_position"])
        if research.get("recent_news"):
            lines.append("近期动态：" + "、".join(research["recent_news"]))
        if plan.get("focus_areas"):
            lines.append("重点考查领域：" + "、".join(plan["focus_areas"]))
        if plan.get("summary"):
            lines.append("面试策略：" + plan["summary"])
        if plan.get("stages"):
            lines.append("定制阶段计划：")
            for i, s in enumerate(plan["stages"], 1):
                goal = s.get("goal") or ""
                focus = "、".join(s.get("focus") or [])
                line = f"  {i}. {s.get('name') or '阶段'}：{goal}"
                if focus:
                    line += f"（关注：{focus}）"
                lines.append(line)
        if not lines:
            return ""
        return "- " + "\n- ".join(lines)

    def _build_candidate_context(self, state: InterviewState) -> str:
        """Render the candidate resume profile as a readable text block."""
        c = state.candidate_profile or {}
        lines = []
        if c.get("name"):
            lines.append(f"姓名：{c['name']}")
        if c.get("years_of_experience"):
            lines.append(f"工作年限：{c['years_of_experience']}")
        if c.get("skills"):
            lines.append("技能/技术栈：" + "、".join(c["skills"]))
        if c.get("work_history"):
            lines.append("工作经历：" + "；".join(c["work_history"]))
        if c.get("projects"):
            lines.append("项目经历：")
            for p in c["projects"]:
                lines.append(f"  - {p}")
        if c.get("highlights"):
            lines.append("亮点/成就：" + "、".join(c["highlights"]))
        if not lines:
            return ""
        return "- " + "\n- ".join(lines)

    def _build_system_prompt(self, state: InterviewState, score_info: dict | None = None) -> str:
        """Build the system prompt for the current state."""
        config = self._get_phase_config(state.phase)
        jd_section = ""
        if state.jd_profile or state.jd_plan:
            jd_section = (
                "## 岗位画像与定制面试计划（务必围绕以下信息出题）\n"
                + self._build_jd_context(state)
            )
        candidate_section = ""
        if state.candidate_profile:
            candidate_section = (
                "## 候选人画像（来自简历，务必结合其真实经历提问）\n"
                + self._build_candidate_context(state)
            )
        score_section = ""
        if score_info:
            score_section = (
                "## 回答质量评估（基于候选人最近一次回答，请据此调整本题难度）\n"
                f"- 质量评分：{score_info['score']}/5；短板提示：{score_info['weakness_hint'] or '无'}\n"
                "- 评分 ≤ 2 → 先追问细节、适当降低难度引导；评分 = 3 → 保持难度并追问一个关键细节；"
                "评分 ≥ 4 → 提升到架构/方案/设计层面的深度问题。"
            )
        return SYSTEM_PROMPT.format(
            role=state.role_title or state.scenario_id,
            phase=state.phase.value,
            phase_description=config["description"],
            question_count=self._count_phase_questions(state, state.phase),
            max_questions=config["max_questions"],
            jd_section=jd_section,
            candidate_section=candidate_section,
            score_section=score_section,
        )

    async def _score_last_answer(self, state: InterviewState) -> dict | None:
        """Score the candidate's most recent answer (1-5) to adapt question difficulty.

        Returns {"score": int, "weakness_hint": str}, or None on any failure —
        callers must not depend on it; the interview proceeds without scoring.
        Adds one short LLM call per answered turn.
        """
        answer = state.get_last_answer()
        if not answer:
            return None
        try:
            from agent.prompts import ANSWER_SCORER_PROMPT
            messages = ANSWER_SCORER_PROMPT.format_messages(
                role=state.role_title or state.scenario_id,
                answer=answer[:2000],
            )
            scorer = self._scorer_runnable()
            if scorer is not None:
                try:
                    res = await scorer.ainvoke(messages)
                    return {
                        "score": max(1, min(5, int(res.score))),
                        "weakness_hint": str(res.weakness_hint or "")[:50],
                    }
                except Exception as e:
                    logger.warning("Structured scoring failed, falling back: %s", e)
            resp = await self.llm.ainvoke(messages)
            content = str(resp.content or "").strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            data = json.loads(content)
            score = int(data.get("score", 3))
            score = max(1, min(5, score))
            return {
                "score": score,
                "weakness_hint": str(data.get("weakness_hint", ""))[:50],
            }
        except Exception as e:
            logger.warning("Answer scoring failed: %s", e)
            return None

    def _build_history(self, state: InterviewState, score_info: dict | None = None) -> list:
        """Build LangChain message history from interview state."""
        messages = [SystemMessage(content=self._build_system_prompt(state, score_info))]
        # Only include the last 10 messages to keep context manageable
        recent = state.messages[-10:] if len(state.messages) > 10 else state.messages
        for msg in recent:
            if msg["role"] == "interviewer":
                messages.append(AIMessage(content=msg["content"]))
            elif msg["role"] == "candidate":
                messages.append(HumanMessage(content=msg["content"]))
        return messages

    async def generate_next(self, state: InterviewState) -> str:
        """Generate the interviewer's next message based on the current state."""
        # Check if we need to transition phases
        if self.should_transition(state):
            old_phase = state.phase
            state.phase = self._next_phase(old_phase)

        score_info = await self._score_last_answer(state)
        messages = self._build_history(state, score_info)
        candidate_answer = state.get_last_answer() or "（面试开始，请面试官先发言）"

        # Add the current prompt
        messages.append(HumanMessage(content=f"候选人的最新回答:\n{candidate_answer}\n\n请根据你的追问规则，给出下一个面试官发言。"))

        response = await self.llm.ainvoke(messages)
        content = response.content

        # Record the interviewer message
        state.add_message("interviewer", content)
        return content

    async def generate_next_stream(self, state: InterviewState) -> AsyncGenerator[str, None]:
        """Stream the interviewer's next message token by token."""
        if self.should_transition(state):
            state.phase = self._next_phase(state.phase)

        score_info = await self._score_last_answer(state)
        messages = self._build_history(state, score_info)
        candidate_answer = state.get_last_answer() or "（面试开始，请面试官先发言）"

        messages.append(HumanMessage(content=f"候选人的最新回答:\n{candidate_answer}\n\n请根据你的追问规则，给出下一个面试官发言。"))

        full_response = ""
        async for chunk in self.llm.astream(messages):
            token = chunk.content if hasattr(chunk, 'content') else str(chunk)
            if token:
                full_response += token
                yield token

        state.add_message("interviewer", full_response)


class EvaluatorAgent:
    """Generates structured evaluation reports after the interview."""

    def __init__(self, llm=None):
        self.llm = llm or get_default_llm()
        self._structured = None  # lazily-built structured-output wrapper (or False)

    def _structured_evaluator(self):
        """Return a `with_structured_output` wrapper, or None if unsupported."""
        if self._structured is None:
            try:
                # DeepSeek lacks json_schema response_format; function calling works.
                self._structured = self.llm.with_structured_output(
                    EvaluationReport, method="function_calling"
                )
            except Exception as e:
                logger.warning("Structured output unavailable, using fallback parsing: %s", e)
                self._structured = False
        return self._structured or None

    async def evaluate(self, state: InterviewState) -> dict:
        """Generate an evaluation report from the interview transcript."""
        from agent.prompts import EVALUATOR_PROMPT

        transcript = _limit_transcript(state.get_transcript())

        structured = self._structured_evaluator()
        if structured is not None:
            try:
                report = await structured.ainvoke(
                    EVALUATOR_PROMPT.format_messages(transcript=transcript)
                )
                return report.to_dict() if hasattr(report, "to_dict") else report
            except Exception as e:
                logger.warning("Structured evaluation failed, falling back: %s", e)

        response = await self.llm.ainvoke(
            EVALUATOR_PROMPT.format_messages(transcript=transcript)
        )
        content = response.content

        # Fallback: parse JSON from the response (with markdown-code-fence handling).
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            return json.loads(content)
        except json.JSONDecodeError:
            return {
                "overall_score": 0,
                "dimension_scores": {},
                "highlights": [],
                "weak_points": [],
                "recommended_topics": [],
                "summary": f"评估解析失败，原始输出: {content[:500]}"
            }
