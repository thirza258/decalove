"""The writing studio's documents are independent of playable game state."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WritingBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: ``image`` is an author's illustration. It travels as context so passage indexes
    #: line up with the client's document, and is never something a model may propose.
    kind: Literal["heading", "dialogue", "narration", "image"]
    text: str = Field(max_length=12000)
    speaker: str = Field(default="", max_length=100)


class AuthorContext(BaseModel):
    """Everything a proposal is grounded in: the brief, the notes, and the draft."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["script", "novel"] = "script"
    title: str = Field(default="Untitled story", max_length=200)
    genre: str = Field(default="Contemporary", max_length=100)
    theme: str = Field(default="", max_length=2000)
    premise: str = Field(default="", max_length=5000)
    characters: str = Field(default="", max_length=5000)
    reference: str = Field(default="", max_length=30000)
    prompt: str = Field(default="", max_length=4000)
    blocks: list[WritingBlock] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def validate_draft(self) -> AuthorContext:
        if sum(len(b.text) + len(b.speaker) for b in self.blocks) > 120000:
            raise ValueError("The draft exceeds 120,000 characters. Work on one chapter at a time.")
        return self


class WritingRequest(AuthorContext):
    action: Literal["starter", "continue", "dialogue", "narrate", "rewrite"] = "starter"
    dialogue_count: int = Field(default=50, ge=1, le=100, strict=True)
    selected_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_context(self) -> WritingRequest:
        if self.selected_index is not None and self.selected_index >= len(self.blocks):
            raise ValueError("The selected passage does not exist.")
        if self.action == "rewrite":
            if self.selected_index is None or not self.blocks[self.selected_index].text.strip():
                raise ValueError("Select a passage with text to rewrite.")
            if self.blocks[self.selected_index].kind == "image":
                raise ValueError("An illustration cannot be rewritten. Select a written passage.")
        return self


class WritingSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=2000)
    blocks: list[WritingBlock] = Field(min_length=1, max_length=220)


class WritingResponse(WritingSuggestion):
    provider: str


#: Shot sizes a storyboard panel can call for, in the language a shot list uses.
SHOTS = ("establishing", "wide", "medium", "close", "insert", "over-shoulder")


class StoryboardPanel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot: Literal["establishing", "wide", "medium", "close", "insert", "over-shoulder"] = "medium"
    title: str = Field(default="", max_length=120)
    description: str = Field(max_length=800)
    dialogue: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=400)


class StoryboardRequest(AuthorContext):
    panel_count: int = Field(default=8, ge=1, le=24, strict=True)


class StoryboardSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=2000)
    panels: list[StoryboardPanel] = Field(min_length=1, max_length=24)


class StoryboardResponse(StoryboardSuggestion):
    provider: str
