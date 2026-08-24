"""Game state — PRD §9.2, §9.3, §16, §27.

The backend is the source of truth (PRD §33). Nothing here is ever written directly from
LLM output; every change goes through the validator and is committed by the engine.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Union

from pydantic import BaseModel, ConfigDict, Field

from app.domain.direction import Directive, PlayerStyle
from app.domain.enums import RELATIONSHIP_AXES, BatchStatus
from app.domain.intent import PlayerIntent
from app.domain.story import RelationshipDelta, StoryStep

FlagValue = Union[str, int, bool]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CharacterState(BaseModel):
    """Live relationship + emotional state for one character — PRD §9.2 / §16."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    relationship: dict[str, int] = Field(default_factory=dict)
    current_emotion: str = "neutral"
    met: bool = False
    last_seen_step: int = -1

    def value(self, axis: str) -> int:
        return int(self.relationship.get(axis, 0))

    def apply(self, delta: RelationshipDelta) -> dict[str, int]:
        """Apply a *validated* delta, clamping each axis to 0..100. Returns what changed."""
        changed: dict[str, int] = {}
        for axis, amount in delta.as_dict().items():
            if not amount:
                continue
            before = self.value(axis)
            after = max(0, min(100, before + amount))
            if after != before:
                self.relationship[axis] = after
                changed[axis] = after - before
        return changed

    def describe(self) -> str:
        """Compact one-line rendering for the LLM prompt."""
        axes = ", ".join(f"{axis} {self.value(axis)}" for axis in RELATIONSHIP_AXES)
        return f"{self.name} [{axes}] feeling {self.current_emotion}"


class WorldState(BaseModel):
    """Where and when we are — PRD §9.3."""

    model_config = ConfigDict(extra="ignore")

    location: str
    time_of_day: str = "morning"
    weekday: str = "Monday"
    day: int = 1
    weather: str = "clear"
    present_characters: list[str] = Field(default_factory=list)
    flags: dict[str, FlagValue] = Field(default_factory=dict)
    inventory: list[str] = Field(default_factory=list)
    arc: str = "prologue"
    active_events: list[str] = Field(default_factory=list)
    completed_events: list[str] = Field(default_factory=list)

    def describe(self) -> str:
        who = ", ".join(self.present_characters) or "nobody else"
        return (
            f"Day {self.day} ({self.weekday}), {self.time_of_day}, weather {self.weather}. "
            f"Location: {self.location}. Present: {who}. Arc: {self.arc}."
        )


class PlayerProfile(BaseModel):
    """Set up once at New Game — PRD §7.1."""

    model_config = ConfigDict(extra="ignore")

    name: str = "You"
    pronouns: str = "they/them"
    tone: str = "warm"
    romance_focus: str | None = None

    def describe(self) -> str:
        focus = self.romance_focus or "undecided"
        return (
            f"{self.name} ({self.pronouns}); preferred story tone: {self.tone}; "
            f"romantic interest: {focus}"
        )


class BatchState(BaseModel):
    """One generation cycle — PRD §12. Surfaced to the client only as 'pending'."""

    model_config = ConfigDict(extra="ignore")

    batch_id: str
    status: BatchStatus = BatchStatus.queued
    source: str = "action"
    error: str | None = None
    step_count: int = 0
    used_fallback: bool = False
    created_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None


class GameSession(BaseModel):
    """The save file — PRD §27.

    ``steps`` is an append-only ledger. The *queue* of §14 is simply the slice after
    ``cursor``; there is no second data structure to keep in sync.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    world_id: str
    player: PlayerProfile = Field(default_factory=PlayerProfile)
    world: WorldState
    characters: dict[str, CharacterState] = Field(default_factory=dict)
    steps: list[StoryStep] = Field(default_factory=list)
    cursor: int = Field(default=-1, description="index of the last step DELIVERED to the player")
    pending: BatchState | None = None
    history: list[str] = Field(default_factory=list)
    last_intent: PlayerIntent | None = None
    #: How this player plays, accumulated across the save (PRD §9.1 pacing).
    style: PlayerStyle = Field(default_factory=PlayerStyle)
    #: The previous run's brief. Read back when planning the next one, so pacing has
    #: memory -- two charged runs never land back to back.
    last_directive: Directive | None = None
    ended: bool = False
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    #: When the PLAYER last advanced the story. Deliberately not ``updated_at``: the
    #: engine writes this document from background batches, failed-batch markers and
    #: asset back-fills, none of which mean anyone is still playing. Garbage collection
    #: reads this field and nothing else.
    last_played_at: datetime = Field(default_factory=_utcnow)

    # -- queue helpers -----------------------------------------------------------------

    @property
    def next_index(self) -> int:
        return len(self.steps)

    @property
    def queued(self) -> list[StoryStep]:
        """Generated-but-not-yet-delivered steps."""
        return self.steps[self.cursor + 1 :]

    @property
    def queue_depth(self) -> int:
        return len(self.steps) - self.cursor - 1

    @property
    def current_step(self) -> StoryStep | None:
        if 0 <= self.cursor < len(self.steps):
            return self.steps[self.cursor]
        return None

    def step_by_id(self, step_id: str) -> StoryStep | None:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    @property
    def awaiting_player(self) -> bool:
        """True when the delivered head is a blocking step the player has not answered."""
        head = self.current_step
        return bool(head and head.is_blocking and self.queue_depth == 0)

    def recent_steps(self, count: int) -> list[StoryStep]:
        return self.steps[max(0, len(self.steps) - count) :]

    def touch(self) -> None:
        """Any write. Called by the repository on every save."""
        self.updated_at = _utcnow()

    def played(self) -> None:
        """The player advanced the story. Only three call sites, all player-driven."""
        self.last_played_at = _utcnow()


class SaveGame(BaseModel):
    """Client-facing save payload — PRD §27's example shape."""

    model_config = ConfigDict(extra="ignore")

    game_id: str
    world_id: str
    current_step: int
    story_arc: str
    world_state: WorldState
    character_states: dict[str, CharacterState]
    flags: dict[str, FlagValue]
    inventory: list[str]
    queue: list[str]
    asset_ids: list[str]
    memories: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=_utcnow)
