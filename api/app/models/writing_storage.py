"""Bounded persisted writing workspaces and their downloadable documents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.writing import WritingBlock


class TextMark(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    kind: Literal["bold", "italic", "underline"]


class DocumentBlock(WritingBlock):
    id: UUID = Field(default_factory=uuid4)
    marks: list[TextMark] = Field(default_factory=list, max_length=2000)
    alignment: Literal["left", "center", "right", "justify"] = "left"
    font: Literal["serif", "sans", "mono"] = "serif"
    size: int = Field(default=16, ge=12, le=32)
    listStyle: Literal["none", "bullet", "number"] = "none"

    @model_validator(mode="after")
    def validate_marks(self) -> DocumentBlock:
        # Browser selections use UTF-16 offsets, including surrogate pairs for emoji.
        length = len(self.text.encode("utf-16-le")) // 2
        if any(mark.end <= mark.start or mark.end > length for mark in self.marks):
            raise ValueError("Formatting must refer to existing text")
        return self


class WritingDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(default="Untitled story", max_length=200)
    format: Literal["script", "novel"] = "script"
    genre: str = Field(default="Contemporary", max_length=100)
    theme: str = Field(default="", max_length=2000)
    premise: str = Field(default="", max_length=5000)
    characters: str = Field(default="", max_length=5000)
    reference: str = Field(default="", max_length=30000)
    prompt: str = Field(default="", max_length=4000)
    dialogueCount: int = Field(default=50, ge=1, le=100, strict=True)
    blocks: list[DocumentBlock] = Field(default_factory=lambda: [DocumentBlock(kind="narration", text="")], max_length=1000)
    updatedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), max_length=40)

    @model_validator(mode="after")
    def validate_blocks(self) -> WritingDocument:
        if len({b.id for b in self.blocks}) != len(self.blocks):
            raise ValueError("Passage IDs must be unique")
        if sum(len(b.text) + len(b.speaker) for b in self.blocks) > 120000:
            raise ValueError("Work on one chapter at a time (up to 120,000 characters)")
        return self


class WritingLibrary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    activeId: UUID
    documents: list[WritingDocument] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_documents(self) -> WritingLibrary:
        ids = {d.id for d in self.documents}
        if self.activeId not in ids or len(ids) != len(self.documents):
            raise ValueError("The active document must exist and document IDs must be unique")
        if len(self.model_dump_json()) > 2_000_000:
            raise ValueError("Workspace is full. Export completed manuscripts to make space.")
        return self


class CourseProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed: list[str] = Field(default_factory=list, max_length=100)
    exercises: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_progress(self) -> CourseProgress:
        if len(self.exercises) > 100 or any(len(k) > 100 or len(v) > 2000 for k, v in self.exercises.items()):
            raise ValueError("Course exercises exceed storage limits")
        if any(len(item) > 100 for item in self.completed):
            raise ValueError("Invalid lesson ID")
        return self


def blank_library() -> WritingLibrary:
    document = WritingDocument()
    return WritingLibrary(activeId=document.id, documents=[document])


class WorkspaceData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    library: WritingLibrary = Field(default_factory=blank_library)
    progress: CourseProgress = Field(default_factory=CourseProgress)


class WorkspaceSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=0)
    data: WorkspaceData


class DocumentFileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: WritingDocument
    format: Literal["txt", "json"]
