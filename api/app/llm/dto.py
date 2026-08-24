"""LLM-facing data transfer objects.

These mirror ``app.domain.story`` but replace every open-ended map with a list of
entries. That is not cosmetic: OpenRouter/OpenAI ``strict`` JSON-schema mode requires
``additionalProperties: false`` on every object, which makes ``dict[str, X]`` illegal.
Keeping the wire shape separate from the domain shape means neither has to compromise.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import RELATIONSHIP_AXES, StepType
from app.domain.story import (
    Choice,
    DialogueLine,
    GeneratedRun,
    GeneratedStep,
    MemoryProposal,
    RelationshipDelta,
    VisualSpec,
)


class EmotionEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    character: str
    emotion: str


class RelationshipChangeEntry(BaseModel):
    """A per-character delta. Small integers only; the validator clamps."""

    model_config = ConfigDict(extra="ignore")
    character: str
    affection: int = 0
    trust: int = 0
    respect: int = 0
    fear: int = 0
    jealousy: int = 0
    friendship: int = 0
    romance: int = 0
    familiarity: int = 0
    anger: int = 0

    def to_delta(self) -> RelationshipDelta:
        return RelationshipDelta(**{axis: getattr(self, axis) for axis in RELATIONSHIP_AXES})


class FlagEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    key: str
    value: str


class LLMDialogue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    speaker: str
    text: str
    emotion: str | None = None


class LLMChoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    text: str


class LLMVisual(BaseModel):
    model_config = ConfigDict(extra="ignore")
    background: str
    character: str | None = None
    expression: str | None = None
    pose: str | None = None
    time_of_day: str | None = None
    weather: str | None = None
    mood: str | None = None
    composition: str | None = None


class LLMMemory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    character: str
    text: str
    importance: float = 0.5
    emotion: str | None = None


class LLMStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    #: Deliberately NOT ``StepType``: the ending is engine-owned. The schema is built once
    #: in ``NarrativeAgent.__init__``, so if ``ending`` were in this enum it would be a
    #: legal value on every single request, and the model could close the story whenever
    #: it felt like wrapping up. Narrowing it here means the wire format cannot express an
    #: ending at all -- the engine promotes the last step of a finale run instead.
    type: Literal["narration", "dialogue", "transition", "event", "choice", "prompt"]
    location: str
    characters: list[str] = Field(default_factory=list)
    narration: str | None = None
    dialogue: LLMDialogue | None = None
    emotions: list[EmotionEntry] = Field(default_factory=list)
    relationship_changes: list[RelationshipChangeEntry] = Field(default_factory=list)
    flags_set: list[FlagEntry] = Field(default_factory=list)
    memory: LLMMemory | None = None
    next_choices: list[LLMChoice] = Field(default_factory=list)
    visual: LLMVisual | None = None

    def to_domain(self) -> GeneratedStep:
        return GeneratedStep(
            type=StepType(self.type),
            location=self.location,
            characters=list(self.characters),
            narration=self.narration,
            dialogue=(
                DialogueLine(
                    speaker=self.dialogue.speaker,
                    text=self.dialogue.text,
                    emotion=self.dialogue.emotion,
                )
                if self.dialogue
                else None
            ),
            emotion={entry.character: entry.emotion for entry in self.emotions},
            relationship_changes={
                entry.character: entry.to_delta() for entry in self.relationship_changes
            },
            flags_set={entry.key: entry.value for entry in self.flags_set},
            memory=(
                MemoryProposal(
                    character=self.memory.character,
                    text=self.memory.text,
                    importance=self.memory.importance,
                    emotion=self.memory.emotion,
                )
                if self.memory
                else None
            ),
            # Blank options are dropped here rather than raising: Choice rejects empty
            # text, and a ValidationError at this point loses the entire generated run to
            # the fallback narrator over one stray option.
            next_choices=[
                Choice(id=c.id, text=c.text) for c in self.next_choices if c.text.strip()
            ],
            visual=(
                VisualSpec(
                    background=self.visual.background,
                    character=self.visual.character,
                    expression=self.visual.expression,
                    pose=self.visual.pose,
                    time_of_day=self.visual.time_of_day,
                    weather=self.visual.weather,
                    mood=self.visual.mood,
                    composition=self.visual.composition,
                )
                if self.visual
                else None
            ),
        )


class LLMRun(BaseModel):
    """The full structured payload one narrative call must return."""

    model_config = ConfigDict(extra="ignore")

    summary: str = ""
    steps: list[LLMStep] = Field(default_factory=list)

    def to_domain(self) -> GeneratedRun:
        return GeneratedRun(summary=self.summary, steps=[s.to_domain() for s in self.steps])
