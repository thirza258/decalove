"""Character memory — PRD §17, and the structured memory model of the intelligence PRD.

A memory is not just a sentence with an embedding. The engine needs to know *what kind*
of event it records, whether it is still unresolved, and how far the player may share it:

``category``    episodic (a thing that happened), relationship (how someone now sees the
                player), or world (a fact about the shared setting).
``status``      a promise stays ``unresolved`` until something in the delivered story
                fulfils or breaks it; contradictory memories can be surfaced because the
                status travels with the text.
``visibility``  who the memory *may* be shown to. Visibility is deliberately separate
                from what a character knows: a public event still has to be witnessed or
                learned before a character may reference it (see ``domain/knowledge.py``).

Retrieval is an in-process cosine scan rather than pgvector; see docs/ARCHITECTURE.md §2
for why that is the right call at MVP scale.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MemoryCategory(str, Enum):
    episodic = "episodic"
    relationship = "relationship"
    world = "world"


class MemoryStatus(str, Enum):
    active = "active"
    fulfilled = "fulfilled"
    broken = "broken"
    resolved = "resolved"
    unresolved = "unresolved"
    superseded = "superseded"


class MemoryVisibility(str, Enum):
    private = "private"
    shared = "shared"
    public = "public"


#: Statuses that must keep being retrieved until the story resolves them. A broken
#: promise that quietly ages out of context is the failure this model exists to stop.
UNRESOLVED_STATUSES: frozenset[MemoryStatus] = frozenset(
    {MemoryStatus.unresolved, MemoryStatus.broken}
)

#: How strongly each unresolved status demands retrieval attention.
_UNRESOLVED_PRIORITY: dict[MemoryStatus, float] = {
    MemoryStatus.unresolved: 1.0,
    MemoryStatus.broken: 1.0,
    MemoryStatus.active: 0.0,
    MemoryStatus.fulfilled: 0.0,
    MemoryStatus.resolved: 0.0,
    MemoryStatus.superseded: 0.0,
}


class CharacterMemory(BaseModel):
    """A thing a character remembers, with provenance and an embedding."""

    model_config = ConfigDict(extra="ignore")

    id: str
    game_id: str
    #: ``character`` is the legacy field name; ``character_id`` is the PRD's. Both are
    #: kept in sync so saves written before this model existed keep loading unchanged.
    character: str
    text: str

    category: MemoryCategory = MemoryCategory.episodic
    #: Free-form event kind: promise, betrayal, gift, argument, confession, discovery...
    event_type: str = ""
    #: Who or what the memory is about. Usually the character, sometimes a place or item.
    subject: str = ""
    visibility: MemoryVisibility = MemoryVisibility.private
    status: MemoryStatus = MemoryStatus.active

    importance: float = 0.5
    emotional_impact: float = 0.0
    emotion: str | None = None
    impact: dict[str, int] = Field(default_factory=dict)
    embedding: list[float] = Field(default_factory=list)

    #: ``step_index`` is the step that produced the memory. ``source_step_id`` is the
    #: engine-owned identity of that step, which is what a trace or a human checks.
    step_index: int = 0
    source_step_id: str = ""
    created_at_step: int = 0
    last_referenced_step: int | None = None
    #: Ids merged into this record by consolidation. Provenance is never discarded.
    merged_from: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def character_id(self) -> str:
        return self.character

    @property
    def description(self) -> str:
        return self.text

    @property
    def unresolved(self) -> bool:
        return self.status in UNRESOLVED_STATUSES

    @property
    def unresolved_priority(self) -> float:
        return _UNRESOLVED_PRIORITY.get(self.status, 0.0)

    def render(self) -> str:
        bits = [self.text]
        if self.emotion:
            bits.append(f"({self.emotion})")
        if self.unresolved:
            bits.append(f"[{self.status.value}]")
        return " ".join(bits)


#: Backwards-compatible alias. Existing repositories, tests and Mongo documents refer to
#: ``MemoryRecord``; the structured model is the same object.
MemoryRecord = CharacterMemory
