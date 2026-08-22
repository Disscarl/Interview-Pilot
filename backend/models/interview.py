"""Interview state model."""
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field


class InterviewPhase(str, Enum):
    INTRO = "intro"
    WARM_UP = "warm_up"
    TECH_1 = "tech_1"
    TECH_2 = "tech_2"
    TECH_3 = "tech_3"
    CLOSING = "closing"
    EVALUATE = "evaluate"


@dataclass
class InterviewState:
    """Holds the full state of an ongoing interview."""
    session_id: str
    scenario_id: str
    user_id: int = 0
    phase: InterviewPhase = InterviewPhase.INTRO
    messages: list[dict] = field(default_factory=list)
    phase_start_ts: float = 0.0
    candidate_name: str = ""
    role_title: str = ""
    jd_profile: Optional[dict] = None
    jd_plan: Optional[dict] = None
    candidate_profile: Optional[dict] = None

    def add_message(self, role: str, content: str, audio_url: str = "", audio_duration: float = 0.0):
        msg = {"role": role, "content": content, "phase": self.phase.value}
        if audio_url:
            msg["audio_url"] = audio_url
        if audio_duration:
            msg["audio_duration"] = audio_duration
        self.messages.append(msg)

    def get_last_answer(self) -> str:
        """Get the candidate's last response."""
        for msg in reversed(self.messages):
            if msg["role"] == "candidate":
                return msg["content"]
        return ""

    def get_transcript(self) -> str:
        """Get the full conversation as a readable transcript."""
        lines = []
        for msg in self.messages:
            role_label = "🤖 面试官" if msg["role"] == "interviewer" else "👤 候选者"
            lines.append(f"{role_label} [{msg['phase']}]: {msg['content']}")
        return "\n\n".join(lines)
