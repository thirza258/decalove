"""Context assembly — the intelligence PRD §6.

Every narrative subsystem feeds one place that decides what the model sees. The
assembly is *prioritised and budgeted*: hard state and the player's own intent are
always present; memories, knowledge, threads and the story ledger compete for the rest.
Anything that does not fit is dropped explicitly and reported, so a trace can say why a
memory did not reach the prompt rather than leaving it a mystery.

Every source is optional. A memory index outage, a slow chronicle or a missing knowledge
store degrades the context; none of them is allowed to cost the player their turn.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.agents.knowledge import CharacterKnowledgeManager
from app.agents.memory_agent import MemoryAgent
from app.agents.planner import NarrativePlanner
from app.domain.chronicle import ChronicleEntry
from app.domain.direction import DecisionContext, Directive
from app.domain.intent import PlayerIntent
from app.domain.knowledge import CharacterKnowledge
from app.domain.memory import CharacterMemory
from app.domain.state import GameSession
from app.domain.threads import NarrativeThread
from app.repositories.base import ChronicleRepository

log = logging.getLogger(__name__)

CHRONICLE_LIMIT = 200
MEMORY_RECALL_TIMEOUT_S = 5.0
SECONDARY_TIMEOUT_S = 2.0

#: Rough chars-per-token for budgeting. Exact tokenisation is the provider's job; this
#: is the same order of magnitude and errs on the side of leaving headroom.
CHARS_PER_TOKEN = 4


@dataclass
class NarrativeContext:
    """The selected context for one run, with provenance for the trace."""

    memories: list[CharacterMemory] = field(default_factory=list)
    knowledge: dict[str, list[CharacterKnowledge]] = field(default_factory=dict)
    threads: list[NarrativeThread] = field(default_factory=list)
    chronicle: list[ChronicleEntry] = field(default_factory=list)
    behavior_note: str = ""
    #: Sections present after budgeting, and those the budget removed.
    included: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    estimated_chars: int = 0
    budget_chars: int = 0

    @property
    def memory_ids(self) -> list[str]:
        return [memory.id for memory in self.memories]

    @property
    def thread_ids(self) -> list[str]:
        return [thread.id for thread in self.threads]

    @property
    def knowledge_counts(self) -> dict[str, int]:
        return {character: len(facts) for character, facts in self.knowledge.items()}

    @property
    def has_knowledge(self) -> bool:
        """False when the store was never read or failed: absence is not ignorance.

        Passing an empty knowledge map to the prompt says "nobody knows anything",
        which is a stronger claim than "the knowledge index was unavailable". The
        distinction matters because the second must degrade to the old behaviour, not
        quietly gag every character.
        """
        return "knowledge" in self.included and bool(self.knowledge)

    @property
    def has_threads(self) -> bool:
        return "threads" in self.included and bool(self.threads)

    def fact_ids(self) -> list[str]:
        return [
            fact.fact_id for facts in self.knowledge.values() for fact in facts
        ]


class ContextAssembler:
    def __init__(
        self,
        *,
        memory: MemoryAgent,
        knowledge: CharacterKnowledgeManager | None = None,
        planner: NarrativePlanner | None = None,
        chronicle: ChronicleRepository | None = None,
        max_chars: int = 24000,
        timeout_s: float = SECONDARY_TIMEOUT_S,
        history_steps: int = 20,
    ) -> None:
        self.memory = memory
        self.knowledge = knowledge
        self.planner = planner
        self.chronicle = chronicle
        self.max_chars = max(4000, max_chars)
        self.timeout_s = timeout_s
        self.history_steps = history_steps

    async def assemble(
        self,
        session: GameSession,
        intent: PlayerIntent,
        decision: DecisionContext,
        directive: Directive,
        *,
        mark_referenced: bool = True,
    ) -> NarrativeContext:
        focus = directive.focus or list(session.world.present_characters)
        query = (
            " ".join(filter(None, [
                intent.summary, intent.raw, decision.chosen_text, decision.typed,
            ]))
            or intent.action
        )

        context = NarrativeContext(budget_chars=self.max_chars)

        try:
            recall = self.memory.recall(
                session.id,
                query,
                characters=focus,
                # The run being written starts at next_index; the reference is to the
                # context that produced it, not to a step the player has read.
                reference_step=session.next_index if mark_referenced else None,
            )
            recalled = await asyncio.wait_for(
                recall, timeout=MEMORY_RECALL_TIMEOUT_S
            )
            # Consolidation normally removes textual duplicates, but it is gated and may
            # lag a delivery. Never spend context on the same sentence twice.
            seen: set[str] = set()
            for record in recalled:
                key = " ".join(record.text.lower().split())
                if key in seen:
                    continue
                seen.add(key)
                context.memories.append(record)
            context.included.append("memories")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("memory recall unavailable for %s", session.id, exc_info=True)
            context.dropped.append("memories")

        if self.knowledge is not None:
            try:
                read = self.knowledge.for_game(session.id)
                context.knowledge = await asyncio.wait_for(read, timeout=self.timeout_s)
                context.included.append("knowledge")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("character knowledge unavailable for %s", session.id, exc_info=True)
                context.dropped.append("knowledge")

        if self.planner is not None:
            try:
                read = self.planner.get_active_threads(session.id)
                context.threads = await asyncio.wait_for(read, timeout=self.timeout_s)
                context.included.append("threads")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("narrative threads unavailable for %s", session.id, exc_info=True)
                context.dropped.append("threads")

        if self.chronicle is not None:
            try:
                read = self.chronicle.for_game(session.id, limit=CHRONICLE_LIMIT)
                context.chronicle = await asyncio.wait_for(read, timeout=self.timeout_s)
                context.included.append("chronicle")
            except asyncio.CancelledError:
                raise
            except Exception:
                # The session still carries its recent run summaries; the prompt falls
                # back to those rather than losing the turn over a slow secondary read.
                log.warning("story chronicle unavailable for %s", session.id, exc_info=True)
                context.dropped.append("chronicle")

        if session.behavior.evidence_count:
            note = session.behavior.note()
            lead = (
                directive.stances[0].character
                if directive.stances
                else (directive.focus[0] if directive.focus else None)
            )
            if note and lead:
                # The same pattern reads differently through the character carrying the
                # scene: the profile is one fact, the interpretation is per person.
                state = session.characters.get(lead)
                warmth = (
                    (state.value("affection") + state.value("trust")) // 2
                    if state is not None else 0
                )
                note = session.behavior.note_for(lead, warmth=warmth)
            context.behavior_note = note
            if note:
                context.included.append("behavior")

        self._fit(context, session)
        return context

    def _fit(self, context: NarrativeContext, session: GameSession) -> None:
        """Drop optional material until the estimate fits the budget.

        Order is priority order reversed: behaviour, then the oldest chronicle scenes,
        then the least relevant memories, then knowledge, then threads. The ledger and
        the player's intent are never dropped entirely.
        """
        def size() -> int:
            estimate = 4000  # the static system prompt and hard state
            estimate += sum(len(memory.render()) for memory in context.memories)
            estimate += sum(
                len(fact.proposition) for facts in context.knowledge.values() for fact in facts
            )
            estimate += sum(len(thread.render()) for thread in context.threads)
            estimate += sum(len(entry.render()) for entry in context.chronicle)
            estimate += len(context.behavior_note)
            return estimate

        if size() <= self.max_chars:
            context.estimated_chars = size()
            return

        if context.behavior_note:
            context.behavior_note = ""
            context.included.remove("behavior")
            context.dropped.append("behavior")
        if context.chronicle and size() > self.max_chars:
            trimmed = 0
            while context.chronicle and size() > self.max_chars:
                # Trim the oldest scenes first. The ledger's own head/tail rendering is
                # what keeps the opening; when the budget cannot afford it, recency wins.
                context.chronicle.pop(0)
                trimmed += 1
            if trimmed:
                context.dropped.append(f"chronicle:{trimmed}")
        if context.memories and size() > self.max_chars:
            trimmed = 0
            while context.memories and size() > self.max_chars:
                context.memories.pop()
                trimmed += 1
            if trimmed:
                context.dropped.append(f"memories:{trimmed}")
        if context.threads and size() > self.max_chars:
            trimmed = 0
            while context.threads and size() > self.max_chars:
                context.threads.pop()
                trimmed += 1
            if trimmed:
                context.dropped.append(f"threads:{trimmed}")
        while context.knowledge and size() > self.max_chars:
            largest = max(context.knowledge, key=lambda key: len(context.knowledge[key]))
            if not context.knowledge[largest]:
                del context.knowledge[largest]
                continue
            context.knowledge[largest].pop(0)
            if not context.knowledge[largest]:
                del context.knowledge[largest]
        context.estimated_chars = size()
        if context.estimated_chars > self.max_chars:
            context.dropped.append("over_budget")
