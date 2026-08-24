"""Provider protocols.

Nothing above this layer knows whether it is talking to OpenRouter or to the offline
scripted narrator. That is what makes the game runnable with no API key.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class LLMError(RuntimeError):
    """Any provider-side failure. Callers degrade to the fallback narrator (PRD §26)."""


class ImageError(RuntimeError):
    """Image generation failed. Callers fall back to placeholder art (PRD §26)."""


@runtime_checkable
class ChatProvider(Protocol):
    name: str

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, Any],
        max_tokens: int = 4096,
        temperature: float = 0.8,
    ) -> dict[str, Any]:
        """Return a JSON object conforming to ``schema``, or raise ``LLMError``."""
        ...


@runtime_checkable
class ImageProvider(Protocol):
    name: str

    async def generate(self, prompt: str, *, width: int = 1024, height: int = 576) -> tuple[bytes, str]:
        """Return ``(image_bytes, content_type)``, or raise ``ImageError``."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...
