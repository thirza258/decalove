"""Character memory — PRD §17."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class MemoryRecord(BaseModel):
    """A thing a character remembers, with an embedding for semantic retrieval.

    Retrieval is an in-process cosine scan rather than pgvector; see
    docs/ARCHITECTURE.md §2 for why that is the right call at MVP scale.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    game_id: str
    character: str
    text: str
    importance: float = 0.5
    emotion: str | None = None
    impact: dict[str, int] = Field(default_factory=dict)
    embedding: list[float] = Field(default_factory=list)
    step_index: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def render(self) -> str:
        bits = [self.text]
        if self.emotion:
            bits.append(f"({self.emotion})")
        return " ".join(bits)
