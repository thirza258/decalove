"""Narrative threads — the intelligence PRD's FR-05.

A thread is a question the story has not finished asking: a broken promise, an
unresolved conflict, a mystery, a character's own goal. Threads are *derived by the
engine* from delivered events and live state, never invented by a model, and the
planner may only keep them available — it cannot force a reconciliation.

The ids are content-derived and stable (``uuid5``), so deriving the same story twice
produces the same thread rather than a duplicate.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ThreadType(str, Enum):
    conflict = "conflict"
    promise = "promise"
    relationship = "relationship"
    mystery = "mystery"
    character_goal = "character_goal"
    world_event = "world_event"


class ThreadStatus(str, Enum):
    active = "active"
    dormant = "dormant"
    resolved = "resolved"
    abandoned = "abandoned"


class NarrativeMilestone(BaseModel):
    """One checkpoint in a thread's progression."""

    model_config = ConfigDict(extra="ignore")

    step_id: str = ""
    step_index: int = 0
    title: str = ""
    achieved: bool = False


class NarrativeThread(BaseModel):
    """A persistent story arc or unresolved thread."""

    model_config = ConfigDict(extra="ignore")

    id: str
    game_id: str

    title: str
    description: str = ""
    thread_type: ThreadType = ThreadType.relationship
    status: ThreadStatus = ThreadStatus.active
    priority: float = 0.5

    involved_characters: list[str] = Field(default_factory=list)

    origin_step_id: str = ""
    origin_step_index: int = 0
    last_progress_step_id: str | None = None
    last_progress_step_index: int | None = None

    milestones: list[NarrativeMilestone] = Field(default_factory=list)
    resolution_conditions: list[dict] = Field(default_factory=list)

    created_at_step: int = 0
    updated_at_step: int = 0

    @property
    def open(self) -> bool:
        return self.status in (ThreadStatus.active, ThreadStatus.dormant)

    def render(self) -> str:
        where = ", ".join(self.involved_characters) or "the world"
        progress = ""
        if self.milestones:
            done = sum(1 for milestone in self.milestones if milestone.achieved)
            progress = f" (milestones {done}/{len(self.milestones)})"
        status = self.status.value
        if self.status is ThreadStatus.dormant:
            status = "dormant — available to reactivate, not active pressure"
        return f"[{self.thread_type.value}/{status} · {where}] {self.title}{progress}"
