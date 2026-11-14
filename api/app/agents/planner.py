"""Narrative Planner — the intelligence PRD's FR-05.

Threads are derived from what the engine already knows: delivered memories, live
relationship state, and what characters know. No model is asked "what should happen
next"; the planner only keeps unresolved questions *available*, so the writer can pick
one up. It can never force a resolution -- a promise is marked resolved only when the
delivered story says so.

Derivation is idempotent. Thread ids are content-derived, and ``sync`` upserts, so a
re-delivered batch updates one thread instead of creating another.
"""

from __future__ import annotations

import logging
import uuid

from app.agents.knowledge import secret_fact_id
from app.content.world import World
from app.domain.knowledge import CharacterKnowledge
from app.domain.memory import CharacterMemory, MemoryStatus
from app.domain.state import GameSession
from app.domain.threads import (
    NarrativeMilestone,
    NarrativeThread,
    ThreadStatus,
    ThreadType,
)
from app.repositories.base import ThreadRepository

log = logging.getLogger(__name__)

#: Anger at or above this is an unresolved conflict worth keeping in view.
CONFLICT_ANGER = 25
#: Anger at or below this is de-escalation; at 0 the conflict is resolved.
CONFLICT_DORMANT_ANGER = 10
#: A thread with no progress for this many delivered steps goes dormant.
DORMANT_AFTER_STEPS = 18
#: How many open threads a prompt may carry.
MAX_ACTIVE_THREADS = 6


def _thread_id(game_id: str, kind: str, subject: str) -> str:
    return uuid.uuid5(
        uuid.NAMESPACE_URL, f"decalove:{game_id}:thread:{kind}:{subject}"
    ).hex


class NarrativePlanner:
    def __init__(
        self,
        repository: ThreadRepository,
        *,
        world: World,
        dormant_after_steps: int = DORMANT_AFTER_STEPS,
    ) -> None:
        self.repository = repository
        self.world = world
        self.dormant_after_steps = max(1, dormant_after_steps)

    # -- reads ---------------------------------------------------------------------------

    async def get_active_threads(self, game_id: str) -> list[NarrativeThread]:
        threads = await self.repository.for_game(game_id)
        active = [thread for thread in threads if thread.status is ThreadStatus.active]
        dormant = [thread for thread in threads if thread.status is ThreadStatus.dormant]
        active.sort(key=lambda thread: thread.priority, reverse=True)
        dormant.sort(key=lambda thread: thread.priority, reverse=True)
        # Dormant threads are capped tighter: they stay available without letting four
        # untouched mysteries crowd out the thread the scene is actually about.
        return (active + dormant[:3])[:MAX_ACTIVE_THREADS]

    def render(self, threads: list[NarrativeThread]) -> str:
        open_threads = [thread for thread in threads if thread.open]
        if not open_threads:
            return "    - (no unresolved threads)"
        lines = [f"    - {thread.render()}" for thread in open_threads]
        lines.append(
            "    These are unresolved questions, not instructions. Keep them available "
            "and let the player's choices move them; never resolve one offscreen or "
            "force a reconciliation they did not ask for."
        )
        return "\n".join(lines)

    def suggestions(self, threads: list[NarrativeThread], session: GameSession) -> str:
        """One deterministic line for the Director's brief."""
        for thread in threads:
            if thread.status is not ThreadStatus.active:
                continue
            if thread.thread_type is ThreadType.promise:
                return (
                    f"An unresolved promise is still open: {thread.title}. If this "
                    "scene makes it relevant, let it cost something -- do not quietly "
                    "fulfil or erase it."
                )
            if thread.thread_type is ThreadType.conflict:
                return (
                    f"Unresolved friction remains: {thread.title}. Let it colour the "
                    "scene if the player is with them; do not force a reconciliation."
                )
            if thread.thread_type is ThreadType.mystery:
                return (
                    f"There is a question the story has not answered: {thread.title}. "
                    "An indirect detail may deepen it; a full reveal needs the player "
                    "to earn it."
                )
        return ""

    # -- derivation ----------------------------------------------------------------------

    async def sync(
        self,
        session: GameSession,
        memories: list[CharacterMemory],
        knowledge: dict[str, list[CharacterKnowledge]] | None = None,
    ) -> list[NarrativeThread]:
        """Re-derive this game's threads from delivered state and persist them.

        Derivation is exhaustive over the current state, so an open thread that no
        longer derives is one whose condition has gone: it is marked resolved rather
        than left to keep influencing the prompt.
        """
        derived = self._derive(session, memories, knowledge or {})
        derived_ids = {thread.id for thread in derived}
        for thread in await self.repository.for_game(session.id):
            if thread.open and thread.id not in derived_ids:
                thread.status = ThreadStatus.resolved
                thread.updated_at_step = session.cursor
                await self.repository.upsert(thread)
        for thread in derived:
            await self.repository.upsert(thread)
        return list(derived)

    def _derive(
        self,
        session: GameSession,
        memories: list[CharacterMemory],
        knowledge: dict[str, list[CharacterKnowledge]],
    ) -> list[NarrativeThread]:
        threads: list[NarrativeThread] = []
        threads.extend(self._promise_threads(session, memories))
        threads.extend(self._conflict_threads(session))
        threads.extend(self._relationship_threads(session, threads))
        threads.extend(self._mystery_threads(session, knowledge))
        return threads

    def _promise_threads(
        self, session: GameSession, memories: list[CharacterMemory]
    ) -> list[NarrativeThread]:
        grouped: dict[tuple[str, str], list[CharacterMemory]] = {}
        for memory in memories:
            if memory.event_type not in ("promise", "commitment", "oath"):
                continue
            if memory.status is MemoryStatus.superseded:
                continue
            grouped.setdefault((memory.character, memory.subject or memory.character), []).append(
                memory
            )

        threads: list[NarrativeThread] = []
        for (character, subject), events in grouped.items():
            events.sort(key=lambda memory: memory.step_index)
            unresolved = [m for m in events if m.unresolved]
            latest = events[-1]
            # The latest delivered account decides. A promise fulfilled in step 6 is not
            # still open because it was also made in step 0; an unresolved event after
            # the resolution reopens it.
            if latest.status in (MemoryStatus.fulfilled, MemoryStatus.resolved):
                status = ThreadStatus.resolved
                description = latest.text
            elif latest.status in (MemoryStatus.unresolved, MemoryStatus.broken):
                status = ThreadStatus.active
                description = latest.text
            elif unresolved:
                status = ThreadStatus.active
                description = unresolved[-1].text
            else:
                status = ThreadStatus.dormant
                description = latest.text

            thread = NarrativeThread(
                id=_thread_id(session.id, "promise", f"{character}:{subject}"),
                game_id=session.id,
                title=f"{self._name(character)}'s promise",
                description=description,
                thread_type=ThreadType.promise,
                status=status,
                priority=0.9 if unresolved else 0.3,
                involved_characters=[character],
                origin_step_id=events[0].source_step_id,
                origin_step_index=events[0].step_index,
                last_progress_step_id=latest.source_step_id,
                last_progress_step_index=latest.step_index,
                milestones=[
                    NarrativeMilestone(
                        step_id=event.source_step_id,
                        step_index=event.step_index,
                        title=event.text[:120],
                        achieved=not event.unresolved,
                    )
                    for event in events[-4:]
                ],
                resolution_conditions=[{"kind": "memory_status_resolved"}],
                created_at_step=events[0].step_index,
                updated_at_step=session.cursor,
            )
            threads.append(self._age(thread, session))
        return threads

    def _conflict_threads(self, session: GameSession) -> list[NarrativeThread]:
        threads: list[NarrativeThread] = []
        for character_id, state in session.characters.items():
            anger = state.value("anger")
            if anger <= 0:
                # Low trust is not a conflict; it is the starting state of most of the
                # cast. A conflict is something the story did, and anger is the axis
                # that records it. If a thread existed before, sync resolves it now.
                continue
            if anger < CONFLICT_DORMANT_ANGER:
                status = ThreadStatus.dormant
            else:
                status = ThreadStatus.active
            if anger >= CONFLICT_ANGER:
                title = f"Unresolved friction with {state.name}"
            else:
                title = f"Something unresolved between the player and {state.name}"
            thread = NarrativeThread(
                id=_thread_id(session.id, "conflict", character_id),
                game_id=session.id,
                title=title,
                description=(
                    f"anger {anger}, trust {state.value('trust')}; the player and "
                    f"{state.name} have not settled this."
                ),
                thread_type=ThreadType.conflict,
                status=status,
                priority=min(1.0, 0.4 + anger / 100),
                involved_characters=[character_id],
                last_progress_step_index=max(0, state.last_seen_step),
                origin_step_index=max(0, state.last_seen_step),
                updated_at_step=session.cursor,
            )
            threads.append(self._age(thread, session))
        return threads

    def _relationship_threads(
        self, session: GameSession, existing: list[NarrativeThread]
    ) -> list[NarrativeThread]:
        conflicted = {
            character
            for thread in existing
            if thread.thread_type is ThreadType.conflict
            for character in thread.involved_characters
        }
        threads: list[NarrativeThread] = []
        for character_id, state in session.characters.items():
            if character_id in conflicted or not state.met:
                continue
            romance = state.value("romance")
            affection = state.value("affection")
            if romance < 40 and affection < 55:
                continue
            thread = NarrativeThread(
                id=_thread_id(session.id, "relationship", character_id),
                game_id=session.id,
                title=f"Where things stand with {state.name}",
                description=(
                    f"affection {affection}, romance {romance}; the player and "
                    f"{state.name} are past the point where this is casual."
                ),
                thread_type=ThreadType.relationship,
                status=ThreadStatus.active,
                priority=min(1.0, 0.3 + max(romance, affection) / 150),
                involved_characters=[character_id],
                last_progress_step_index=max(0, state.last_seen_step),
                updated_at_step=session.cursor,
            )
            threads.append(self._age(thread, session))
        return threads

    def _mystery_threads(
        self,
        session: GameSession,
        knowledge: dict[str, list[CharacterKnowledge]],
    ) -> list[NarrativeThread]:
        threads: list[NarrativeThread] = []
        for character in self.world.characters:
            if not character.secret:
                continue
            fid = secret_fact_id(session.id, character.id)
            disclosed = any(
                fact.fact_id == fid
                for holder, facts in knowledge.items()
                if holder != character.id
                for fact in facts
            )
            if disclosed:
                continue
            state = session.characters.get(character.id)
            if state is None or not state.met:
                continue
            thread = NarrativeThread(
                id=_thread_id(session.id, "mystery", character.id),
                game_id=session.id,
                title=f"What {character.name} has not said",
                description=(
                    "A private thing this character carries. It may surface through "
                    "habit or deflection long before it is spoken."
                ),
                thread_type=ThreadType.mystery,
                # Dormant until there is enough trust for a disclosure to be plausible.
                status=(
                    ThreadStatus.active
                    if state.value("trust") >= 45 and state.value("familiarity") >= 45
                    else ThreadStatus.dormant
                ),
                priority=0.5 if state.value("trust") >= 45 else 0.2,
                involved_characters=[character.id],
                last_progress_step_index=max(0, state.last_seen_step),
                updated_at_step=session.cursor,
            )
            threads.append(self._age(thread, session))
        return threads

    def _age(self, thread: NarrativeThread, session: GameSession) -> NarrativeThread:
        """Dormancy is a function of distance from the last progress, not a guess."""
        if thread.status is not ThreadStatus.active:
            return thread
        last = thread.last_progress_step_index
        if last is None:
            return thread
        if session.cursor - last >= self.dormant_after_steps:
            thread.status = ThreadStatus.dormant
        return thread

    def _name(self, character_id: str) -> str:
        character = self.world.character(character_id)
        return character.name if character else character_id
