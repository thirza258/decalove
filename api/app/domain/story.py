"""Story step schema — PRD §13.

Two models, deliberately split (PRD §33: *the LLM generates the narrative, but the game
engine owns the state*):

``GeneratedStep``
    What the LLM is allowed to emit. No ids, no asset URLs, no absolute stat values —
    only proposals.

``StoryStep``
    What the backend persists and serves. Adds engine-owned identity (``step_id``,
    ``index``, ``batch_id``) and resolved visual assets.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import RELATIONSHIP_AXES, AssetStatus, StepType

FlagValue = Union[str, int, bool]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Choice(BaseModel):
    """One option on a blocking ``choice`` step."""

    model_config = ConfigDict(extra="ignore")

    id: str
    text: str

    @field_validator("text")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("choice text must not be empty")
        return v.strip()


class DialogueLine(BaseModel):
    model_config = ConfigDict(extra="ignore")

    speaker: str = Field(description="character id, or 'player' for a line the player chose")
    text: str
    emotion: str | None = None


class RelationshipDelta(BaseModel):
    """Per-step *change* to a character's relationship axes.

    Deltas only — never absolute values. The validator clamps these
    (PRD §24 Rule 4: no ``affection: 40 -> 100`` without an appropriate event).
    """

    model_config = ConfigDict(extra="ignore")

    affection: int = 0
    trust: int = 0
    respect: int = 0
    fear: int = 0
    jealousy: int = 0
    friendship: int = 0
    romance: int = 0
    familiarity: int = 0
    anger: int = 0

    def as_dict(self) -> dict[str, int]:
        return {axis: getattr(self, axis) for axis in RELATIONSHIP_AXES}

    def is_zero(self) -> bool:
        return all(v == 0 for v in self.as_dict().values())

    def clamped(self, limit: int) -> tuple["RelationshipDelta", list[str]]:
        """Return a copy with every axis clamped to ±``limit``, plus the axes that moved."""
        offenders: list[str] = []
        values: dict[str, int] = {}
        for axis, value in self.as_dict().items():
            capped = max(-limit, min(limit, int(value)))
            if capped != value:
                offenders.append(f"{axis}={value}->{capped}")
            values[axis] = capped
        return RelationshipDelta(**values), offenders


class MemoryProposal(BaseModel):
    """A durable memory the narrative agent thinks a character should keep — PRD §17."""

    model_config = ConfigDict(extra="ignore")

    character: str
    text: str
    importance: float = 0.5
    emotion: str | None = None

    @field_validator("importance")
    @classmethod
    def _bounded(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class VisualSpec(BaseModel):
    """What the scene should look like — PRD §13 ``visual`` / §18.

    Also the cache key material for asset reuse (PRD §19).
    """

    model_config = ConfigDict(extra="ignore")

    background: str = Field(description="location id, or an explicit background key")
    character: str | None = None
    expression: str | None = None
    pose: str | None = None
    time_of_day: str | None = None
    weather: str | None = None
    mood: str | None = None
    composition: str | None = None


class AssetRef(BaseModel):
    """Pointer to a generated image. ``status`` tells the client whether to fall back."""

    model_config = ConfigDict(extra="ignore")

    cache_key: str
    status: AssetStatus = AssetStatus.pending
    asset_id: str | None = None
    url: str | None = None


class GeneratedStep(BaseModel):
    """A single beat as proposed by the LLM. Engine-owned fields are deliberately absent."""

    model_config = ConfigDict(extra="ignore")

    type: StepType
    location: str
    characters: list[str] = Field(default_factory=list)
    narration: str | None = None
    dialogue: DialogueLine | None = None
    emotion: dict[str, str] = Field(default_factory=dict)
    relationship_changes: dict[str, RelationshipDelta] = Field(default_factory=dict)
    flags_set: dict[str, FlagValue] = Field(default_factory=dict)
    memory: MemoryProposal | None = None
    next_choices: list[Choice] = Field(default_factory=list)
    visual: VisualSpec | None = None

    @property
    def is_blocking(self) -> bool:
        return self.type.is_blocking

    @property
    def is_terminal(self) -> bool:
        return self.type.is_terminal

    @property
    def is_ending(self) -> bool:
        return self.type is StepType.ending

    def text_body(self) -> str:
        """All player-visible prose in this step, for moderation and agency checks."""
        parts = [self.narration or ""]
        if self.dialogue:
            parts.append(self.dialogue.text)
        parts.extend(choice.text for choice in self.next_choices)
        return "\n".join(p for p in parts if p)


class GeneratedRun(BaseModel):
    """What one LLM call returns: a linear run of beats ending at a player decision."""

    model_config = ConfigDict(extra="ignore")

    steps: list[GeneratedStep] = Field(default_factory=list)
    summary: str = Field(default="", description="one-sentence recap, used to compact history")


class StoryStep(GeneratedStep):
    """A persisted, engine-owned step. This is what Ren'Py receives.

    Immutable on purpose. A 300-step save is deep-copied on every repository read, and at
    that length the copy dominates the request (measured: ~2.9 ms per copy at 400 steps,
    ~98 ms of event-loop time per four-second long poll). Freezing the steps lets the
    in-memory repository share them between clones instead, which is only *provably* safe
    if nothing can mutate one after it is stored.

    Amend a stored step with ``step.model_copy(update={...})`` and put the result back in
    the ledger. ``GeneratedStep`` stays mutable -- the validator repairs those in place
    before they ever become a ``StoryStep``.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    step_id: str
    index: int
    batch_id: str
    created_at: datetime = Field(default_factory=_utcnow)
    background_asset: AssetRef | None = None
    character_asset: AssetRef | None = None
    fallback: bool = Field(
        default=False,
        description="True when this step came from the scripted fallback narrator (PRD §26).",
    )
