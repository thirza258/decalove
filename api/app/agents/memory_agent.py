"""Character memory — PRD §17, evolved into the intelligence PRD's Memory Manager.

Write path: the narrative agent proposes a memory, the engine commits it *when the step
is delivered* (so an undelivered or discarded run leaves no trace). The proposal carries
category, status and visibility, so an unresolved promise survives as one.

Read path: a hybrid blend of semantic relevance, importance, recency, relationship
relevance and unresolved-event priority. The weights are configurable because they are a
product decision, not a constant of nature. Two floors keep the failure players actually
notice from happening -- the *significant* memory being forgotten -- while still letting
relevance choose among equally significant ones:

* unresolved promises and conflicts are always ranked as if they mattered now;
* a highly important memory does not vanish merely because it is old.

Consolidation merges duplicate memories into a surviving record and marks the others
``superseded``. It never deletes, and it never lets a duplicate collapse an unresolved
event into a resolved one.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass

from app.domain.memory import (
    CharacterMemory,
    MemoryCategory,
    MemoryStatus,
    MemoryVisibility,
)
from app.domain.story import MemoryProposal
from app.llm.base import EmbeddingProvider
from app.llm.embeddings import HashingEmbedding, cosine
from app.repositories.base import MemoryRepository

log = logging.getLogger(__name__)

#: PRD §5.4 defaults. Every weight is normalised to [0, 1] before it is applied.
SEMANTIC_WEIGHT = 0.35
IMPORTANCE_WEIGHT = 0.20
RECENCY_WEIGHT = 0.15
RELATIONSHIP_WEIGHT = 0.20
UNRESOLVED_WEIGHT = 0.10

#: A memory at or above this importance is never dropped purely for being old.
HIGH_IMPORTANCE_FLOOR = 0.8
#: The score below which an important-or-unresolved memory is lifted. Chosen above the
#: ceiling of an ordinary recent memory (0.2×importance + 0.15×recency + 0.2×relationship
#: ≈ 0.45 at default weights) so a flood of small talk cannot bury one.
RETENTION_FLOOR = 0.55

#: Duplicate detection: token-set similarity at or above this, for the same character
#: and event type, merges two memories.
DUPLICATE_SIMILARITY = 0.85


@dataclass(frozen=True)
class MemoryWeights:
    semantic: float = SEMANTIC_WEIGHT
    importance: float = IMPORTANCE_WEIGHT
    recency: float = RECENCY_WEIGHT
    relationship: float = RELATIONSHIP_WEIGHT
    unresolved: float = UNRESOLVED_WEIGHT

    def normalised(self) -> "MemoryWeights":
        semantic = max(0.0, self.semantic)
        importance = max(0.0, self.importance)
        recency = max(0.0, self.recency)
        relationship = max(0.0, self.relationship)
        unresolved = max(0.0, self.unresolved)
        total = semantic + importance + recency + relationship + unresolved
        if total <= 0:
            return MemoryWeights()
        return MemoryWeights(
            semantic=semantic / total,
            importance=importance / total,
            recency=recency / total,
            relationship=relationship / total,
            unresolved=unresolved / total,
        )


@dataclass
class ConsolidationReport:
    merged: int = 0
    superseded: int = 0
    contradictions: int = 0
    kept: int = 0

    def __str__(self) -> str:  # pragma: no cover - log formatting
        return (
            f"merged {self.merged}, superseded {self.superseded}, "
            f"contradictions {self.contradictions}, kept {self.kept}"
        )


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9']+", text.lower()) if len(token) > 2}


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 1.0 if left.strip().lower() == right.strip().lower() else 0.0
    return len(a & b) / len(a | b)


def _normalise_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


class MemoryAgent:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        repository: MemoryRepository,
        *,
        top_k: int = 6,
        embedding_timeout_s: float = 1.0,
        weights: MemoryWeights | None = None,
        token_budget: int = 1200,
    ) -> None:
        self.embedder = embedder
        self.repository = repository
        self.top_k = top_k
        self.embedding_timeout_s = embedding_timeout_s
        self.weights = (weights or MemoryWeights()).normalised()
        #: Character budget for the memories a prompt may carry. Retrieval is budgeted
        #: because an irrelevant memory is not free: it costs context and attention.
        self.token_budget = token_budget
        self._embedding_retry_at = 0.0

    async def _vector(self, text: str) -> list[float]:
        """Embeddings improve retrieval; an outage must not stop story delivery."""
        if time.monotonic() < self._embedding_retry_at:
            return []
        try:
            vectors = await asyncio.wait_for(
                self.embedder.embed([text]), timeout=self.embedding_timeout_s,
            )
            return vectors[0] if vectors else []
        except asyncio.CancelledError:
            raise
        except Exception:
            # A batch can carry several memories. Pay for one failed attempt, not one
            # full timeout per beat while holding the game's delivery lock.
            self._embedding_retry_at = time.monotonic() + 30.0
            log.warning("memory embeddings unavailable; using text recall", exc_info=True)
            return []

    # -- write path ----------------------------------------------------------------------

    async def remember(
        self,
        game_id: str,
        proposal: MemoryProposal,
        *,
        step_index: int,
        impact: dict[str, int] | None = None,
        source_step_id: str = "",
    ) -> CharacterMemory:
        vector = await self._vector(proposal.text)

        def _enum(enum_type, value, fallback):
            try:
                return enum_type(value)
            except (TypeError, ValueError):
                return fallback

        # The text is part of the identity: one step can establish more than one fact,
        # and re-delivering the same step must still land on the same ids. Hashing the
        # normalised text gives both properties without a second lookup.
        fingerprint = hashlib.sha1(
            _normalise_text(proposal.text).encode("utf-8")
        ).hexdigest()[:12]
        record = CharacterMemory(
            id=uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"decalove:{game_id}:{step_index}:{proposal.character}:{fingerprint}",
            ).hex,
            game_id=game_id,
            character=proposal.character,
            text=proposal.text,
            category=_enum(MemoryCategory, proposal.category, MemoryCategory.episodic),
            event_type=proposal.event_type or "",
            subject=proposal.subject or proposal.character,
            visibility=_enum(MemoryVisibility, proposal.visibility, MemoryVisibility.private),
            status=_enum(MemoryStatus, proposal.status, MemoryStatus.active),
            importance=proposal.importance,
            emotional_impact=proposal.importance if proposal.emotion else 0.0,
            emotion=proposal.emotion,
            impact=dict(impact or {}),
            embedding=vector,
            step_index=step_index,
            source_step_id=source_step_id,
            created_at_step=step_index,
            metadata={"proposed_category": proposal.category, "proposed_status": proposal.status},
        )
        await self.repository.add(record)
        return record

    # -- read path -----------------------------------------------------------------------

    async def recall(
        self,
        game_id: str,
        query: str,
        *,
        characters: list[str] | None = None,
        top_k: int | None = None,
        context: dict | None = None,
        token_budget: int | None = None,
        reference_step: int | None = None,
    ) -> list[CharacterMemory]:
        """Retrieve the memories this scene should carry.

        ``context`` may carry ``relationship`` values for the focus characters; they
        are used only to weight relationship-shaped memories, never to change state.
        ``reference_step``, when given, records that the chosen memories were actually
        put in front of the writer -- best-effort, and never on the critical path.
        """
        records = await self.repository.for_game(game_id)
        # Superseded duplicates stay stored for provenance but must not consume context.
        records = [record for record in records if record.status is not MemoryStatus.superseded]
        if not records:
            return []

        focus = set(characters or [])
        if focus:
            focused = [r for r in records if r.character in focus or r.subject in focus]
            # Only narrow if the focus actually has history; otherwise keep the whole pool.
            records = focused or records

        limit = top_k or self.top_k
        query_vector = await self._vector(query or "")
        newest = max((r.step_index for r in records), default=0) or 1

        if query_vector and all(len(r.embedding) == len(query_vector) for r in records):
            raw = [cosine(query_vector, r.embedding) for r in records]
        else:
            # Re-embed BOTH sides locally. Mixing hosted vectors and hashed vectors of
            # the same dimension produces convincing but meaningless similarities.
            lexical = HashingEmbedding()
            query_vector = lexical.embed_one(query or "")
            raw = [cosine(query_vector, lexical.embed_one(r.text)) for r in records]
        # Sparse hashed vectors produce small absolute cosines (0.05-0.30), which a raw
        # weighted sum would let importance and recency drown out entirely. Rescaling to
        # the candidate pool keeps relevance the dominant term where it should be.
        low, high = min(raw), max(raw)
        span = high - low

        ranked = sorted(
            zip(records, raw),
            key=lambda pair: self.score(
                pair[0], pair[1], low=low, span=span, newest=newest, focus=focus
            ),
            reverse=True,
        )
        chosen: list[CharacterMemory] = []
        budget = token_budget if token_budget is not None else self.token_budget
        used = 0
        for record, _ in ranked:
            if len(chosen) >= limit:
                break
            cost = max(1, len(record.text) // 4)
            if chosen and used + cost > budget:
                # The first result is always returned: a strictly empty answer helps
                # nobody, and a one-line memory is cheaper than the miss.
                continue
            chosen.append(record)
            used += cost

        if reference_step is not None and chosen:
            await self._mark_referenced(chosen, reference_step)
        return chosen

    async def _mark_referenced(
        self, records: list[CharacterMemory], step_index: int
    ) -> None:
        """Record that these memories reached a prompt. Diagnostic, never load-bearing."""
        changed = [
            record for record in records
            if record.last_referenced_step != step_index
        ]
        if not changed:
            return
        for record in changed:
            record.last_referenced_step = step_index
        try:
            await asyncio.gather(
                *(self.repository.replace(record) for record in changed),
                return_exceptions=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            # A read is not allowed to fail because an observability write did.
            log.warning("could not record memory references", exc_info=True)

    def score(
        self,
        record: CharacterMemory,
        similarity: float,
        *,
        low: float = 0.0,
        span: float = 1.0,
        newest: int = 1,
        focus: set[str] | None = None,
    ) -> float:
        """The hybrid retrieval score for one record.

        Public because the weights and retention floors are a product decision worth
        testing directly rather than inferring from a ranking of synthetic memories.
        """
        focus = focus or set()

        def semantic() -> float:
            return (similarity - low) / span if span > 1e-9 else 0.0

        def relationship() -> float:
            # 1.0 when the memory is about someone in this scene, 0.5 when there is no
            # focus at all. A memory that recorded a real relationship move gets a small
            # extra weight: that is what "relationship relevance" means in practice.
            base = (
                1.0 if (focus and (record.character in focus or record.subject in focus))
                else 0.5
            )
            return min(1.0, base + 0.25) if record.impact else base

        def recency() -> float:
            return min(1.0, record.step_index / newest) if newest else 0.0

        value = (
            self.weights.semantic * semantic()
            + self.weights.importance * record.importance
            + self.weights.recency * recency()
            + self.weights.relationship * relationship()
            + self.weights.unresolved * record.unresolved_priority
        )
        # Retention floors. Both classes are the memories a player notices being
        # forgotten, so similarity alone must not be able to bury them.
        if record.unresolved or record.importance >= HIGH_IMPORTANCE_FLOOR:
            value = max(value, RETENTION_FLOOR)
        return value

    async def retrieve(
        self,
        game_id: str,
        query: str,
        *,
        character_id: str | None = None,
        context: dict | None = None,
    ) -> list[CharacterMemory]:
        """The PRD §8.1 Memory Manager interface, over the same hybrid recall."""
        return await self.recall(
            game_id,
            query,
            characters=[character_id] if character_id else None,
            context=context,
        )

    # -- consolidation -------------------------------------------------------------------

    async def consolidate(self, game_id: str) -> ConsolidationReport:
        """Merge duplicates, surface contradictions, and preserve unresolved events.

        Deterministic and safe to run on every delivery: the ids are stable, the
        survivor is picked by importance then age, and ``superseded`` records are kept
        with their provenance rather than removed.
        """
        records = [
            record
            for record in await self.repository.for_game(game_id)
            if record.status is not MemoryStatus.superseded
        ]
        report = ConsolidationReport()
        consumed: set[str] = set()

        for index, keeper in enumerate(records):
            if keeper.id in consumed:
                continue
            for other in records[index + 1:]:
                if other.id in consumed or other.character != keeper.character:
                    continue
                # Contradiction is checked before duplication: two accounts of the same
                # event can use different words precisely because they disagree, so a
                # lexical similarity gate would miss every real contradiction.
                if self._contradicts(keeper, other):
                    report.contradictions += 1
                    keeper.metadata["contradicts"] = sorted(
                        {*_as_list(keeper.metadata.get("contradicts")), other.id}
                    )
                    other.metadata["contradicts"] = sorted(
                        {*_as_list(other.metadata.get("contradicts")), keeper.id}
                    )
                    await self.repository.replace(keeper)
                    await self.repository.replace(other)
                    continue
                if not self._same_event(keeper, other):
                    continue

                survivor = keeper if keeper.importance >= other.importance else other
                loser = other if survivor is keeper else keeper
                if survivor.status not in (MemoryStatus.unresolved, MemoryStatus.broken) and (
                    loser.status in (MemoryStatus.unresolved, MemoryStatus.broken)
                ):
                    # An unresolved event must never be merged down into a resolved one.
                    survivor.status = loser.status
                survivor.importance = max(keeper.importance, other.importance)
                survivor.merged_from = sorted(
                    {*survivor.merged_from, *loser.merged_from, loser.id}
                )
                survivor.metadata["merged"] = True
                loser.status = MemoryStatus.superseded
                loser.metadata["superseded_by"] = survivor.id
                consumed.add(loser.id)
                if survivor is not keeper:
                    # The survivor was later in the list; the outer loop keeps scanning
                    # the original keeper's position, so the merged keeper is consumed.
                    consumed.add(keeper.id)
                await self.repository.replace(survivor)
                await self.repository.replace(loser)
                keeper = survivor
                report.merged += 1
                report.superseded += 1

        report.kept = len(records) - report.superseded
        return report

    @staticmethod
    def _same_event(left: CharacterMemory, right: CharacterMemory) -> bool:
        if not left.event_type or left.event_type != right.event_type:
            # Without an event type, only an unambiguous textual duplicate counts.
            return _normalise_text(left.text) == _normalise_text(right.text) or (
                _similarity(left.text, right.text) >= 0.95
            )
        if left.subject and right.subject and left.subject != right.subject:
            return False
        return _similarity(left.text, right.text) >= DUPLICATE_SIMILARITY

    @staticmethod
    def _contradicts(left: CharacterMemory, right: CharacterMemory) -> bool:
        """Two records of the same event that cannot both be true."""
        if not left.event_type or left.event_type != right.event_type:
            return False
        if left.subject != right.subject:
            return False
        conflicting = (MemoryStatus.fulfilled, MemoryStatus.broken)
        return left.status in conflicting and right.status in conflicting and (
            left.status is not right.status
        )


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []
