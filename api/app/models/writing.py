"""The writing studio's documents are independent of playable game state."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WritingBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["heading", "dialogue", "narration"]
    text: str = Field(max_length=12000)
    speaker: str = Field(default="", max_length=100)


class WritingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["starter", "continue", "dialogue", "narrate", "rewrite"] = "starter"
    format: Literal["script", "novel"] = "script"
    title: str = Field(default="Untitled story", max_length=200)
    genre: str = Field(default="Contemporary", max_length=100)
    theme: str = Field(default="", max_length=2000)
    premise: str = Field(default="", max_length=5000)
    characters: str = Field(default="", max_length=5000)
    reference: str = Field(default="", max_length=30000)
    prompt: str = Field(default="", max_length=4000)
    dialogue_count: int = Field(default=50, ge=1, le=100, strict=True)
    blocks: list[WritingBlock] = Field(default_factory=list, max_length=1000)
    selected_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_context(self) -> WritingRequest:
        if sum(len(b.text) + len(b.speaker) for b in self.blocks) > 120000:
            raise ValueError("The draft exceeds 120,000 characters. Work on one chapter at a time.")
        if self.selected_index is not None and self.selected_index >= len(self.blocks):
            raise ValueError("The selected passage does not exist.")
        if self.action == "rewrite" and (
            self.selected_index is None or not self.blocks[self.selected_index].text.strip()
        ):
            raise ValueError("Select a passage with text to rewrite.")
        return self


class WritingSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=2000)
    blocks: list[WritingBlock] = Field(min_length=1, max_length=220)


class WritingResponse(WritingSuggestion):
    provider: str

