"""Offline image provider.

Synthesises a deterministic gradient from the scene's palette instead of calling a model.
It is not art, but it makes the *pipeline* real: prompts are built, cache keys are
computed and honoured (PRD §19), bytes are stored, and Ren'Py loads them over HTTP.
"""

from __future__ import annotations

import hashlib

from app.assets.png import gradient_png

_PALETTES = (
    ("#ff9e7d", "#2b3a67"),
    ("#f0c987", "#4a3b2a"),
    ("#8fd1a0", "#243b2e"),
    ("#9b8bd4", "#1a1726"),
    ("#7fb2e5", "#1c2b3a"),
    ("#e05a72", "#3b1f2b"),
)


class PlaceholderImageProvider:
    name = "placeholder"

    def __init__(self, *, palette: tuple[str, str] | None = None) -> None:
        self._palette = palette

    async def generate(self, prompt: str, *, width: int = 1024, height: int = 576) -> tuple[bytes, str]:
        if self._palette:
            top, bottom = self._palette
        else:
            digest = hashlib.blake2b(prompt.encode("utf-8"), digest_size=4).digest()
            top, bottom = _PALETTES[digest[0] % len(_PALETTES)]
        # Render small and let the client scale: this is a stand-in, not a deliverable.
        return gradient_png(min(width, 512), min(height, 288), top, bottom, seed=prompt), "image/png"
