"""Provider protocols.

Nothing above this layer knows whether it is talking to OpenRouter or to the offline
scripted narrator. That is what makes the game runnable with no API key.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Protocol, runtime_checkable


#: Token usage for the current ``complete_json`` call. A ContextVar rather than an
#: attribute on the provider: two games can be generating concurrently in one process,
#: and a shared field would attribute one player's tokens to the other's trace.
_CURRENT_USAGE: ContextVar[dict[str, int] | None] = ContextVar(
    "llm_current_usage", default=None
)
_USAGE_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


def reset_usage() -> None:
    """Called once at the start of a provider call, before any retries it makes."""
    _CURRENT_USAGE.set({key: 0 for key in _USAGE_KEYS})


def record_usage(usage: dict[str, Any] | None) -> None:
    """Accumulate one HTTP response's usage into the current call.

    Accumulates because a call may be a repair round-trip or a free-model retry; the
    trace wants what the turn cost, not what the last attempt cost.
    """
    if not usage:
        return
    current = dict(_CURRENT_USAGE.get() or {key: 0 for key in _USAGE_KEYS})
    for key in _USAGE_KEYS:
        value = usage.get(key)
        if isinstance(value, (int, float)):
            current[key] = current.get(key, 0) + int(value)
    _CURRENT_USAGE.set(current)


def take_usage() -> dict[str, int]:
    """Read and clear the current call's usage. Empty when the provider reports none."""
    value = _CURRENT_USAGE.get() or {}
    _CURRENT_USAGE.set(None)
    return {key: int(value.get(key, 0)) for key in _USAGE_KEYS}


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

    async def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 576,
        seed: int | None = None,
        negative: str | None = None,
    ) -> tuple[bytes, str]:
        """Return ``(image_bytes, content_type)``, or raise ``ImageError``.

        ``seed`` fixes the starting noise so the same subject comes back looking like
        itself; ``negative`` names what to suppress. Both are hints -- a backend that
        cannot honour them ignores them rather than failing.
        """
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...
