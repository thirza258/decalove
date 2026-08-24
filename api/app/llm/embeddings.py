"""Embeddings for character memory retrieval — PRD §17.

OpenRouter is a chat gateway and does not expose an embeddings endpoint, so the default
is a deterministic hashed-n-gram vectoriser: no key, no network, no extra service. At MVP
scale (a handful of characters, tens of memories per save) a cosine scan over these is
both fast and good enough for lexical recall like *"did the player defend Aiko?"*.

``HttpEmbedding`` is the seam for any OpenAI-compatible ``/embeddings`` endpoint when
better semantics are wanted.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import httpx

from app.llm.base import LLMError

_WORD = re.compile(r"[a-z0-9']+")


def _normalise(token: str) -> str:
    """Fold possessives and simple plurals together.

    Without this, ``brother's`` and ``brother`` hash to different buckets and a query
    about someone's brother scores exactly zero against the memory that mentions him.
    """
    token = token.strip("'")
    if token.endswith("'s"):
        token = token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        token = token[:-1]
    return token


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    # Vectors from HashingEmbedding are already unit length; normalise defensively anyway.
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class HashingEmbedding:
    """Hashed unigrams + bigrams, sublinear term frequency, L2-normalised."""

    name = "hashing"

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]

    def embed_one(self, text: str) -> list[float]:
        tokens = [t for t in (_normalise(w) for w in _WORD.findall((text or "").lower())) if t]
        grams = list(tokens) + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        counts: dict[int, float] = {}
        for gram in grams:
            # blake2b, not hash(): Python's hash() is salted per process, which would make
            # stored embeddings unreadable after a restart.
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            counts[bucket] = counts.get(bucket, 0.0) + sign

        vector = [0.0] * self.dimensions
        for bucket, value in counts.items():
            magnitude = 1.0 + math.log(abs(value)) if abs(value) > 1 else abs(value)
            vector[bucket] = math.copysign(magnitude, value)

        norm = math.sqrt(sum(v * v for v in vector))
        if norm:
            vector = [v / norm for v in vector]
        return vector


class HttpEmbedding:
    """Any OpenAI-compatible ``POST {base_url}/embeddings`` service."""

    name = "http"

    def __init__(self, *, base_url: str, api_key: str, model: str, dimensions: int, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self.dimensions = dimensions
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                json={"model": self._model, "input": texts},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMError(f"embedding request failed: {exc}") from exc
        return [item["embedding"] for item in payload.get("data", [])]

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
