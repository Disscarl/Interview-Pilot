"""Pydantic schemas for structured LLM output (evaluation report + answer score).

Used with `with_structured_output` so the model output is validated at the
boundary instead of hand-parsed with json.loads + regex fence-stripping.
"""
from pydantic import BaseModel, Field


class AnswerScore(BaseModel):
    """Per-answer quality score used to adapt question difficulty."""

    score: int = Field(default=3, ge=1, le=5, description="1=完全没答上 … 5=深入且有独到见解")
    weakness_hint: str = Field(default="", max_length=50, description="30字以内一句话短板提示")


class ReportDimension(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str = Field(default="")


class WeakPoint(BaseModel):
    area: str = Field(default="")
    description: str = Field(default="")
    suggestion: str = Field(default="")


class EvaluationReport(BaseModel):
    """Full evaluation report shape (matches what the frontend renders)."""

    overall_score: float = Field(ge=0, le=5)
    dimension_scores: dict[str, ReportDimension] = Field(default_factory=dict)
    highlights: list[str] = Field(default_factory=list)
    weak_points: list[WeakPoint] = Field(default_factory=list)
    recommended_topics: list[str] = Field(default_factory=list)
    summary: str = Field(default="")

    def to_dict(self) -> dict:
        return self.model_dump()
