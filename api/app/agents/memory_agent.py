"""Character memory — PRD §17.

Write path: the narrative agent proposes a memory, the engine commits it *when the step
is delivered* (so an undelivered or discarded run leaves no trace).

Read path: cosine similarity over stored embeddings, blended with the memory's own
importance and how recently it happened. A pure similarity ranking surfaces the most
lexically-similar memory; players notice the *significant* one being forgotten.
"""

from __future__ import annotations

import uuid

from app.domain.memory import MemoryRecord
from app.domain.story import MemoryProposal
from app.llm.base import EmbeddingProvider
from app.llm.embeddings import cosine
from app.repositories.base import MemoryRepository

SIMILARITY_WEIGHT = 0.60
IMPORTANCE_WEIGHT = 0.30
RECENCY_WEIGHT = 0.10


class MemoryAgent:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        repository: MemoryRepository,
        *,
        top_k: int = 6,
    ) -> None:
        self.embedder = embedder
        self.repository = repository
        self.top_k = top_k

    async def remember(
        self,
        game_id: str,
        proposal: MemoryProposal,
        *,
        step_index: int,
        impact: dict[str, int] | None = None,
    ) -> MemoryRecord:
        vectors = await self.embedder.embed([proposal.text])
        record = MemoryRecord(
            id=uuid.uuid4().hex,
            game_id=game_id,
            character=proposal.character,
            text=proposal.text,
            importance=proposal.importance,
            emotion=proposal.emotion,
            impact=dict(impact or {}),
            embedding=vectors[0] if vectors else [],
            step_index=step_index,
        )
        await self.repository.add(record)
        return record

    async def recall(
        self,
        game_id: str,
        query: str,
        *,
        characters: list[str] | None = None,
        top_k: int | None = None,
    ) -> list[MemoryRecord]:
        records = await self.repository.for_game(game_id)
        if not records:
            return []

        if characters:
            wanted = set(characters)
            focused = [r for r in records if r.character in wanted]
            # Only narrow if the focus actually has history; otherwise keep the whole pool.
            records = focused or records

        limit = top_k or self.top_k
        vectors = await self.embedder.embed([query or ""])
        query_vector = vectors[0] if vectors else []
        newest = max((r.step_index for r in records), default=0) or 1

        raw = [cosine(query_vector, r.embedding) if query_vector else 0.0 for r in records]
        # Sparse hashed vectors produce small absolute cosines (0.05-0.30), which a raw
        # weighted sum would let importance and recency drown out entirely. Rescaling to
        # the candidate pool keeps relevance the dominant term where it should be.
        low, high = min(raw), max(raw)
        span = high - low

        def score(record: MemoryRecord, similarity: float) -> float:
            relevance = (similarity - low) / span if span > 1e-9 else 0.0
            recency = min(1.0, record.step_index / newest) if newest else 0.0
            return (
                SIMILARITY_WEIGHT * relevance
                + IMPORTANCE_WEIGHT * record.importance
                + RECENCY_WEIGHT * recency
            )

        ranked = sorted(
            zip(records, raw), key=lambda pair: score(pair[0], pair[1]), reverse=True
        )
        return [record for record, _ in ranked[:limit]]
