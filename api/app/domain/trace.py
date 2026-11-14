"""Generation traces — the intelligence PRD's FR-08.

One record per generation attempt, holding *what the model was given and what came
back* in a form that can be compared across prompt versions and models. Traces are
diagnostic: a failed trace write must never cost the player their turn, and none of the
story text is required for delivery once the run is committed.

Player prose is included because it is the input that caused the run and the only way to
reproduce a complaint; the save already stores it in the chronicle. Bounds keep a trace
small enough to keep for a whole playthrough.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

MAX_TEXT_CHARS = 600


def _clip(text: str | None, limit: int = MAX_TEXT_CHARS) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class NarrativeTrace(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    game_id: str
    batch_id: str = ""
    step_index: int = 0

    # -- what went in ---------------------------------------------------------------
    player_input: str = ""
    intent: dict = Field(default_factory=dict)
    memory_ids: list[str] = Field(default_factory=list)
    memory_count: int = 0
    knowledge_facts: dict[str, int] = Field(default_factory=dict)
    knowledge_fact_ids: list[str] = Field(default_factory=list)
    thread_ids: list[str] = Field(default_factory=list)
    context_sections: list[str] = Field(default_factory=list)
    prompt_version: str = ""
    provider: str = ""
    model: str = ""
    director: dict = Field(default_factory=dict)

    # -- what came out --------------------------------------------------------------
    output_steps: int = 0
    output_summary: str = ""
    validator_rules: list[str] = Field(default_factory=list)
    used_fallback: bool = False
    quality: dict = Field(default_factory=dict)
    repair_attempts: int = 0

    # -- cost and outcome -----------------------------------------------------------
    prompt_chars: int = 0
    output_chars: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    committed: bool = False
    delivered: bool = False
    error: str = ""

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def clipped_input(self) -> str:
        return _clip(self.player_input)
