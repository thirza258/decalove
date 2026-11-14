"""Narrative quality evaluation — the intelligence PRD's FR-03.

The deterministic Validator remains the authority on what may be committed. This report
is a *second opinion*: it measures how good the writing is within the rules, and it can
ask for at most one targeted repair. A repair that fails deterministic validation is
discarded, so quality scoring can never widen what the engine accepts.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class QualityDimension(str, Enum):
    character_voice = "character_voice"
    context_relevance = "context_relevance"
    emotional_continuity = "emotional_continuity"
    causality = "causality"
    player_agency = "player_agency"
    repetition = "repetition"
    narrative_progression = "narrative_progression"
    choice_quality = "choice_quality"
    knowledge_consistency = "knowledge_consistency"


DIMENSIONS: tuple[QualityDimension, ...] = tuple(QualityDimension)


class QualityIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dimension: QualityDimension
    severity: str = "medium"  # low | medium | high
    description: str = ""
    step_index: int | None = None

    @property
    def repairable(self) -> bool:
        return self.severity in ("medium", "high")


class NarrativeQualityReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    overall_score: float = 1.0
    scores: dict[str, float] = Field(default_factory=dict)
    issues: list[QualityIssue] = Field(default_factory=list)
    repairable: bool = False
    recommended_repairs: list[str] = Field(default_factory=list)
    #: ``rubric`` is the deterministic offline evaluator; ``llm`` is the refined model
    #: pass when one is configured. Recorded so a regression can be attributed.
    evaluator: str = "rubric"
    model: str | None = None
    latency_ms: float = 0.0
    #: Usage of the optional judge call, kept separate from generation usage so the two
    #: costs can be attributed (PRD §5.16: record evaluation latency and consumption).
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def passes(self, threshold: float) -> bool:
        return self.overall_score >= threshold and not any(
            issue.severity == "high" for issue in self.issues
        )
