"""Coach Agent — post-interview debrief.

Consumes the evaluation report + transcript (produced by the evaluator) and
produces a coach debrief: weak-point analysis, a study plan, and the next
interview's opening question targeted at the weakest areas. This is the third
agent role in the multi-agent orchestration (interviewer / evaluator / coach).
"""
import json
import logging

from models.schemas import CoachReport
from services.llm import get_default_llm

logger = logging.getLogger("interview-pilot")

EMPTY_COACH = {
    "summary": "教练复盘生成失败，请稍后重试。",
    "weak_analysis": [],
    "study_plan": [],
    "next_focus": [],
    "next_first_question": "",
}


class CoachAgent:
    """Generates a structured coach debrief after an interview."""

    def __init__(self, llm=None):
        self.llm = llm or get_default_llm()
        self._structured = None  # lazily-built structured-output wrapper (or False)

    def _structured_coach(self):
        if self._structured is None:
            try:
                self._structured = self.llm.with_structured_output(
                    CoachReport, method="function_calling"
                )
            except Exception as e:
                logger.warning("Structured coach unavailable, using fallback parsing: %s", e)
                self._structured = False
        return self._structured or None

    async def generate(self, transcript: str, report: dict) -> dict:
        """Produce the coach debrief from the transcript + evaluation report."""
        from agent.prompts import COACH_PROMPT

        messages = COACH_PROMPT.format_messages(
            report_json=json.dumps(report or {}, ensure_ascii=False),
            transcript=transcript,
        )
        structured = self._structured_coach()
        if structured is not None:
            try:
                res = await structured.ainvoke(messages)
                data = res.model_dump() if hasattr(res, "model_dump") else res
                if isinstance(data, dict):
                    return data
                logger.warning("Structured coach returned non-dict: %s", type(data).__name__)
            except Exception as e:
                logger.warning("Structured coach generation failed, falling back: %s", e)

        resp = await self.llm.ainvoke(messages)
        content = str(getattr(resp, "content", None) or "")
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return data
            logger.warning("Coach JSON was not an object: %s", type(data).__name__)
        except (json.JSONDecodeError, ValueError):
            pass
        return EMPTY_COACH
