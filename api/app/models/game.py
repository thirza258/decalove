"""HTTP request/response models for the Game API — PRD §22."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import BatchStatus
from app.domain.state import BatchState, CharacterState, PlayerProfile, WorldState
from app.domain.story import StoryStep


class NewGameRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    world_id: str | None = None
    player_name: str = Field(default="You", max_length=40)
    pronouns: str = Field(default="they/them", max_length=40)
    tone: str = Field(default="warm", max_length=60)
    romance_focus: str | None = None


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input: str = Field(min_length=1, max_length=600)


class SkipRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    until_step: int = Field(default=19, ge=0)


class ChoiceRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_id: str
    choice_id: str


class IntentOut(BaseModel):
    action: str
    target: str | None = None
    emotion: str | None = None
    risk: str = "medium"
    meaningful: bool = True


class AcceptedOut(BaseModel):
    """202 body for actions and choices — generation happens in the background."""

    game_id: str
    batch_id: str | None = None
    status: BatchStatus | None = None
    intent: IntentOut | None = None


class GameStateOut(BaseModel):
    """Everything the client needs *except* the step ledger, which can be long."""

    game_id: str
    world_id: str
    player: PlayerProfile
    world: WorldState
    characters: dict[str, CharacterState]
    current_step_index: int
    queue_depth: int
    awaiting_player: bool
    ended: bool
    pending: BatchState | None = None
    recent_summary: list[str] = Field(default_factory=list)


class NextStepOut(BaseModel):
    """The playback loop's whole vocabulary.

    ``pending`` is the only interesting one: it means "keep the player busy". The Ren'Py
    client answers it with an in-world ambient line, never a spinner (PRD §11).
    """

    status: Literal["ready", "pending", "awaiting_player", "ended"]
    step: StoryStep | None = None
    queue_depth: int = 0
    retry_after_ms: int = 700
    ambience: list[str] = Field(default_factory=list)


class StepsBatchOut(BaseModel):
    """Batch of steps delivered at once so the Ren'Py client can loop locally without per-click requests."""

    status: Literal["ready", "pending", "awaiting_player", "ended"]
    steps: list[StoryStep] = Field(default_factory=list)
    queue_depth: int = 0
    retry_after_ms: int = 700
    ambience: list[str] = Field(default_factory=list)


class CharacterOut(BaseModel):
    id: str
    name: str
    pronouns: str
    role: str
    expressions: list[str]
    palette: list[str]


class LocationOut(BaseModel):
    id: str
    name: str
    description: str
    palette: list[str]
    ambience: list[str]


class WorldOut(BaseModel):
    """Served once at boot so the client can draw consistent placeholder art offline."""

    id: str
    title: str
    premise: str
    tone: str
    rating: str
    opening_location: str
    characters: list[CharacterOut]
    locations: list[LocationOut]
