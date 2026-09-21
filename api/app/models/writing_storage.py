"""Bounded persisted writing workspaces and their downloadable documents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, get_args
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.writing import SHOTS, WritingBlock

#: One palette for coloured words, highlights and notes. The client renders each name
#: as a CSS class, so a document can never carry a colour value into a style attribute.
MarkColor = Literal["green", "teal", "blue", "violet", "plum", "crimson", "amber", "slate"]
MARK_COLORS: tuple[str, ...] = get_args(MarkColor)

#: Uploaded illustrations. Raster only: an SVG served inline from the API's own origin
#: would be a script the workspace link could be tricked into running.
IMAGE_TYPES: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),
    "image/gif": (b"GIF87a", b"GIF89a"),
}
IMAGE_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}


def is_image(payload: bytes, content_type: str) -> bool:
    """Whether the bytes are the picture they claim to be. A declared type is a hint."""
    if content_type == "image/webp":  # "RIFF" then the file size, then the format tag.
        return payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"
    return any(payload.startswith(signature) for signature in IMAGE_TYPES.get(content_type, ()))

#: 5 MB of picture, which is ~6.7 MB of base64 -- comfortably inside the 12 MB the
#: nginx proxy accepts for a workspace payload.
MAX_IMAGE_BYTES = 5_000_000

#: Hand-uploaded pictures anyone in this deployment may insert. See docs/IMAGES.md.
LIBRARY_PREFIX = "writing/library/"


class TextMark(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    kind: Literal["bold", "italic", "underline", "color", "highlight"]
    value: MarkColor | None = None

    @model_validator(mode="after")
    def validate_value(self) -> TextMark:
        if (self.value is None) is (self.kind in ("color", "highlight")):
            raise ValueError("Colour and highlight marks name a palette colour; other marks do not")
        return self


class BlockImage(BaseModel):
    """A picture in the asset store. Its bytes never travel inside the workspace."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[0-9a-f]{64}$")
    alt: str = Field(default="", max_length=300)
    width: int = Field(default=100, ge=20, le=100)


class DocumentBlock(WritingBlock):
    id: UUID = Field(default_factory=uuid4)
    marks: list[TextMark] = Field(default_factory=list, max_length=2000)
    alignment: Literal["left", "center", "right", "justify"] = "left"
    font: Literal["serif", "sans", "mono"] = "serif"
    size: int = Field(default=16, ge=12, le=32)
    listStyle: Literal["none", "bullet", "number"] = "none"
    image: BlockImage | None = None

    @model_validator(mode="after")
    def validate_marks(self) -> DocumentBlock:
        # Browser selections use UTF-16 offsets, including surrogate pairs for emoji.
        length = len(self.text.encode("utf-16-le")) // 2
        if any(mark.end <= mark.start or mark.end > length for mark in self.marks):
            raise ValueError("Formatting must refer to existing text")
        if (self.image is None) is (self.kind == "image"):
            raise ValueError("Only an image passage carries a picture, and it must carry one")
        return self


class DocumentNote(BaseModel):
    """A writer's own note: research, a reminder, a line kept for later."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(default="", max_length=120)
    body: str = Field(default="", max_length=2000)
    color: MarkColor | None = None
    updatedAt: str = Field(default="", max_length=40)


class DocumentComment(BaseModel):
    """A remark on a passage. ``blockId`` may dangle: passages are deleted freely, and
    losing the remark with the paragraph would be worse than showing it unanchored."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    blockId: UUID | None = None
    quote: str = Field(default="", max_length=160)
    author: str = Field(default="", max_length=60)
    body: str = Field(default="", max_length=1000)
    resolved: bool = False
    createdAt: str = Field(default="", max_length=40)


class DocumentPanel(BaseModel):
    """One storyboard frame: what we see, and what is said while we see it."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    shot: Literal[SHOTS] = "medium"  # type: ignore[valid-type]
    title: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=800)
    dialogue: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=400)
    image: BlockImage | None = None


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
    notes: list[DocumentNote] = Field(default_factory=list, max_length=30)
    comments: list[DocumentComment] = Field(default_factory=list, max_length=100)
    storyboard: list[DocumentPanel] = Field(default_factory=list, max_length=40)
    updatedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), max_length=40)

    @model_validator(mode="after")
    def validate_blocks(self) -> WritingDocument:
        if len({b.id for b in self.blocks}) != len(self.blocks):
            raise ValueError("Passage IDs must be unique")
        if len({p.id for p in self.storyboard}) != len(self.storyboard):
            raise ValueError("Storyboard panel IDs must be unique")
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


class ImageUploadRequest(BaseModel):
    """A picture the writer chose, carried as base64 beside its declared type."""

    model_config = ConfigDict(extra="forbid")

    content_type: Literal["image/png", "image/jpeg", "image/webp", "image/gif"]
    #: 5 MB of bytes is at most 6,834,000 characters of base64, newlines included.
    data: str = Field(min_length=1, max_length=6_900_000)
    alt: str = Field(default="", max_length=300)


class LibraryImageRequest(BaseModel):
    """Adopts a picture placed in the asset store by hand -- see docs/IMAGES.md."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=len(LIBRARY_PREFIX) + 1, max_length=300)

    @model_validator(mode="after")
    def validate_key(self) -> LibraryImageRequest:
        suffix = self.key[len(LIBRARY_PREFIX):]
        if not self.key.startswith(LIBRARY_PREFIX) or ".." in self.key or suffix.startswith("/"):
            raise ValueError("Library pictures live under writing/library/")
        if self.key.rsplit(".", 1)[-1].lower() not in set(IMAGE_EXTENSIONS.values()) | {"jpeg"}:
            raise ValueError("Library pictures are .png, .jpg, .webp or .gif files")
        return self
