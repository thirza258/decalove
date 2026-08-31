"""An image provider that tries several backends in order.

``IMAGE_BACKEND=sdxl,openrouter`` renders on the local GPU and falls back to the hosted API
when there is no GPU, the weights are missing, or a pass fails. The chain is a *preference
order*, not a load balancer: the first backend that returns an image wins, and a backend is
only skipped when it raises.

Why this rather than one backend at a time: the two failure modes are unrelated. A GPU box
loses SDXL to a driver upgrade or an OOM; a hosted model goes down or rate-limits. Either
alone leaves the player looking at placeholder art for as long as the outage lasts, and the
other one was sitting right there.
"""

from __future__ import annotations

import logging
from typing import Sequence

from app.llm.base import ImageError, ImageProvider

log = logging.getLogger(__name__)


def _name_of(provider: ImageProvider) -> str:
    return getattr(provider, "name", type(provider).__name__)


class FallbackImageProvider:
    """``ImageProvider`` over an ordered chain of other providers."""

    def __init__(self, providers: Sequence[ImageProvider]) -> None:
        if not providers:
            raise ValueError("a fallback chain needs at least one provider")
        self._providers: list[ImageProvider] = list(providers)
        #: Reported by /health and stored on every AssetRecord, so "which backend am I
        #: actually on" stays a one-request question. Which link produced a given image
        #: is in the log line below rather than the name, because the name has to be
        #: stable across calls.
        self.name = "+".join(_name_of(provider) for provider in self._providers)

    async def generate(
        self, prompt: str, *, width: int = 1024, height: int = 576
    ) -> tuple[bytes, str]:
        failures: list[str] = []
        for provider in self._providers:
            label = _name_of(provider)
            try:
                result = await provider.generate(prompt, width=width, height=height)
            except ImageError as exc:
                failures.append(f"{label}: {exc}")
                log.warning("image backend %s failed, trying the next: %s", label, exc)
                continue
            if failures:
                log.info("image backend %s served the request after %d failure(s)", label, len(failures))
            return result

        # Every link is out. AssetService turns this into status="unavailable" and the
        # client draws its built-in placeholder, so the story is never blocked on art.
        raise ImageError("every image backend failed -- " + "; ".join(failures))

    async def aclose(self) -> None:
        for provider in self._providers:
            closer = getattr(provider, "aclose", None)
            if closer is not None:
                await closer()
