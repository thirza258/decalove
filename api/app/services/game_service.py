"""Game orchestration — the API's whole surface, in one place.

The rule that makes branching safe (docs/ARCHITECTURE.md §4): **state is committed when a
step is delivered to the player, not when it is generated.** A generated-but-unread run
has changed nothing, so discarding it costs nothing.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from app.agents.director import DirectorAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.narrative import NarrativeAgent
from app.agents.visual import VisualAgent
from app.content.world import World
from app.domain.direction import DecisionContext, DecisionKind
from app.domain.enums import TIMES_OF_DAY, WEEKDAYS, BatchStatus, StepType
from app.domain.intent import PlayerIntent
from app.domain.state import (
    BatchState,
    CharacterState,
    GameSession,
    PlayerProfile,
    SaveGame,
    WorldState,
)
from app.domain.story import StoryStep
from app.models.game import GameStateOut, NextStepOut
from app.repositories.base import GameRepository
from app.services.asset_service import AssetService
from app.services.generation import GenerationService

log = logging.getLogger(__name__)

POLL_INTERVAL_S = 0.12


class GameNotFound(LookupError):
    pass


class InvalidAction(ValueError):
    pass


class GameService:
    def __init__(
        self,
        *,
        world: World,
        games: GameRepository,
        director: DirectorAgent,
        narrative: NarrativeAgent,
        memory: MemoryAgent,
        visual: VisualAgent,
        assets: AssetService,
        generation: GenerationService,
        max_wait_ms: int = 10000,
        steps_per_arc: int = 40,
    ) -> None:
        self.world = world
        self.games = games
        self.director = director
        self.narrative = narrative
        self.memory = memory
        self.visual = visual
        self.assets = assets
        self.generation = generation
        self.max_wait_ms = max_wait_ms
        self.steps_per_arc = max(1, steps_per_arc)
        #: Games with a self-heal continuation already spawned. Needed because _kick
        #: runs while holding the game lock, so the submit() it spawns cannot claim
        #: `pending` until this call returns -- and the next poll would otherwise see
        #: the same dry queue and kick again.
        self._kicked: set[str] = set()

    # -- lifecycle -----------------------------------------------------------------------

    async def create_game(self, profile: PlayerProfile, world_id: str | None = None) -> GameSession:
        world = self.world
        opening = world.location(world.opening_location) or world.locations[0]
        session = GameSession(
            id=uuid.uuid4().hex,
            world_id=world.id,
            player=profile,
            world=WorldState(
                location=opening.id,
                time_of_day=opening.times[0] if opening.times else "morning",
                present_characters=list(world.character_ids),
                arc=world.arcs[0] if world.arcs else "prologue",
            ),
            characters={
                character.id: CharacterState(
                    id=character.id,
                    name=character.name,
                    relationship=dict(character.starting_relationship),
                    current_emotion=character.default_emotion,
                )
                for character in world.characters
            },
        )
        await self.games.create(session)

        # The opening is authored, so New Game is instant and every run starts strong.
        result = self.narrative.opening(session)
        opening_intent = PlayerIntent(
            action="begin", risk="low", summary="the story begins", raw=""
        )
        await self.generation.commit_run(
            session.id,
            BatchState(batch_id="opening", status=BatchStatus.ready, source="opening"),
            result,
            opening_intent,
            self.director.plan(
                session,
                opening_intent,
                DecisionContext(kind=DecisionKind.opening),
                max_steps=self.narrative.max_steps,
            ),
        )
        refreshed = await self.games.get(session.id)
        return refreshed or session

    async def get(self, game_id: str) -> GameSession:
        session = await self.games.get(game_id)
        if session is None:
            raise GameNotFound(game_id)
        return session

    async def delete(self, game_id: str) -> bool:
        self.forget(game_id)
        return await self.games.delete(game_id)

    def forget(self, game_id: str) -> None:
        """Drop per-game bookkeeping so it does not outlive the save itself."""
        self._kicked.discard(game_id)
        self.generation.forget(game_id)

    async def list_ids(self, limit: int = 50) -> list[str]:
        return await self.games.list_ids(limit)

    # -- playback ------------------------------------------------------------------------

    async def next_step(self, game_id: str, wait_ms: int = 0) -> NextStepOut:
        """Deliver the next step, optionally waiting briefly for one to appear.

        Short long-polling is what keeps generation invisible: the client receives the
        first beat the instant it exists rather than on the next poll boundary (PRD §11).
        """
        deadline = time.monotonic() + min(max(0, wait_ms), self.max_wait_ms) / 1000.0

        while True:
            outcome = await self._try_deliver(game_id)
            if outcome.status != "pending" or time.monotonic() >= deadline:
                return outcome
            await asyncio.sleep(POLL_INTERVAL_S)

    async def _try_deliver(self, game_id: str) -> NextStepOut:
        async with self.generation.lock(game_id):
            session = await self.games.get(game_id)
            if session is None:
                raise GameNotFound(game_id)

            # An ended game is ended, even if steps were still queued when it ended.
            # Checking this only on an empty queue meant the ending could be overtaken
            # by beats written before it.
            if session.ended:
                head = session.current_step
                # Carry the ending step so a client that reconnects to a finished save can
                # render the closing beat without a second request.
                return NextStepOut(
                    status="ended",
                    step=head if (head and head.is_ending) else None,
                    queue_depth=session.queue_depth,
                )

            if session.queue_depth == 0:
                # Order matters. A batch in flight is checked BEFORE awaiting_player:
                # right after the player answers a decision point the head of the ledger
                # is still that same blocking step, so testing awaiting_player first
                # would re-offer the choice they just made. Whether that is visible
                # depends only on how long generation takes -- which is precisely the
                # thing that is fast offline and slow with a real model.
                if session.pending and session.pending.status in (
                    BatchStatus.queued,
                    BatchStatus.running,
                ):
                    # A batch is claimed; submit()'s own guard takes over from here.
                    self._kicked.discard(game_id)
                    return NextStepOut(
                        status="pending",
                        queue_depth=0,
                        ambience=self._ambience(session),
                        retry_after_ms=700,
                    )

                if session.awaiting_player:
                    # Reached with no batch in flight, which also covers a failed batch:
                    # re-offering the decision point is the right recovery (PRD §26).
                    self._kicked.discard(game_id)
                    return NextStepOut(
                        status="awaiting_player",
                        step=session.current_step,
                        queue_depth=0,
                    )

                # The ledger ran dry without leaving a decision point. Rather than
                # dead-end the player, ask the engine for a continuation.
                log.info("game %s ran dry; requesting a continuation", game_id)
                self._kick(session.id)
                return NextStepOut(
                    status="pending",
                    queue_depth=0,
                    ambience=self._ambience(session),
                    retry_after_ms=300,
                )

            self._kicked.discard(game_id)
            session.cursor += 1
            step = session.steps[session.cursor]
            await self._commit_step(session, step)
            session.played()
            await self.games.save(session)
            return NextStepOut(status="ready", step=step, queue_depth=session.queue_depth)

    def _kick(self, game_id: str) -> None:
        """Self-heal a dry queue by submitting a low-key continuation.

        Deliberately does not set ``pending`` here: ``submit()`` does that under the lock,
        and setting it early would make submit() mistake the placeholder for a batch that
        is already running and skip the work entirely. ``_kicked`` covers that gap --
        without it, every poll arriving before submit() claims the lock kicks again.
        """
        if game_id in self._kicked:
            return
        self._kicked.add(game_id)
        self.generation._spawn(self._continue(game_id))  # noqa: SLF001 - one task owner

    async def _continue(self, game_id: str) -> None:
        batch = None
        try:
            batch = await self.generation.submit(
                game_id,
                PlayerIntent(action="observe", risk="low", summary="the moment continues", raw=""),
                decision=DecisionContext(kind=DecisionKind.auto),
            )
        finally:
            if batch is None:
                # Nothing was queued, so release the guard and let a later poll retry.
                self._kicked.discard(game_id)

    async def _commit_step(self, session: GameSession, step: StoryStep) -> None:
        """Apply a delivered step's proposals to the source of truth."""
        for character_id, delta in step.relationship_changes.items():
            state = session.characters.get(character_id)
            if state is not None:
                state.apply(delta)

        for character_id, mood in step.emotion.items():
            state = session.characters.get(character_id)
            if state is not None:
                state.current_emotion = mood

        if step.flags_set:
            session.world.flags.update(step.flags_set)

        if step.characters:
            session.world.present_characters = list(step.characters)
            for character_id in step.characters:
                state = session.characters.get(character_id)
                if state is not None:
                    state.met = True
                    state.last_seen_step = step.index

        if step.type is StepType.transition and step.location != session.world.location:
            session.world.location = step.location
            self._advance_clock(session, step.location)

        self._advance_arc(session)

        if step.is_ending:
            # Committed on DELIVERY, like every other state change. A generated-but-unread
            # ending has not happened.
            session.ended = True
            log.info(
                "game %s ended (%s)", session.id, session.world.flags.get("ending", "unknown")
            )

        if step.memory:
            impact = {
                axis: value
                for axis, value in (
                    step.relationship_changes.get(step.memory.character).as_dict().items()
                    if step.memory.character in step.relationship_changes
                    else []
                )
                if value
            }
            await self.memory.remember(
                session.id, step.memory, step_index=step.index, impact=impact
            )

    def _advance_clock(self, session: GameSession, location_id: str) -> None:
        """Move time forward on a scene change, snapping to a time the place supports.

        A scene change advancing the clock is the standard visual-novel convention, and
        without it a save sits in the same hour forever -- which also means every rooftop
        scene resolves to one cached sunset, quietly defeating the time-keyed asset cache
        of PRD §19.

        Monotonic by construction: it only looks forward, and rolls the day when the
        destination has no remaining slot today.
        """
        location = self.world.location(location_id)
        allowed = tuple(location.times) if (location and location.times) else TIMES_OF_DAY

        try:
            start = TIMES_OF_DAY.index(session.world.time_of_day) + 1
        except ValueError:
            start = 0

        later_today = [slot for slot in TIMES_OF_DAY[start:] if slot in allowed]
        if later_today:
            session.world.time_of_day = later_today[0]
            return

        session.world.day += 1
        session.world.weekday = WEEKDAYS[(session.world.day - 1) % len(WEEKDAYS)]
        session.world.time_of_day = next(
            (slot for slot in TIMES_OF_DAY if slot in allowed), TIMES_OF_DAY[0]
        )

    def _advance_arc(self, session: GameSession) -> None:
        """Move through the world's arcs as the save gets longer.

        Without this the arc is whatever ``create_game`` set, so the arc guidance handed
        to the writer is a constant for the life of a playthrough and four of the five
        authored arc notes are unreachable.
        """
        arcs = self.world.arcs
        if not arcs:
            return
        index = min(len(arcs) - 1, max(0, session.cursor) // self.steps_per_arc)

        # Only ever forward. Lowering STEPS_PER_ARC on a running deployment, or an arc set
        # by hand, must not walk a save back into a chapter it has already finished.
        if session.world.arc in arcs and index <= arcs.index(session.world.arc):
            return

        if arcs[index] != session.world.arc:
            if session.world.arc and session.world.arc not in session.world.completed_events:
                session.world.completed_events.append(session.world.arc)
            session.world.arc = arcs[index]
            log.info("game %s entered arc %s", session.id, arcs[index])

    def _ambience(self, session: GameSession) -> list[str]:
        location = self.world.location(session.world.location)
        return list(location.ambience) if location else []

    # -- player input --------------------------------------------------------------------

    async def submit_action(self, game_id: str, text: str) -> tuple[BatchState | None, PlayerIntent]:
        session = await self.get(game_id)
        if session.ended:
            raise InvalidAction("this game has ended")

        # Stamped before parsing, not after: parsing can be a multi-second model call,
        # and a player returning after eight days would otherwise sit in that window with
        # a save the collector still considers abandoned.
        async with self.generation.lock(game_id):
            current = await self.games.get(game_id)
            if current is None:
                raise GameNotFound(game_id)
            current.played()
            await self.games.save(current)

        intent = await self.director.parse(session, text)
        head = session.current_step
        decision = DecisionContext(
            kind=DecisionKind.free_text,
            step_id=head.step_id if head else None,
            typed=text.strip(),
            # They had options in front of them and wrote their own line instead. That is
            # a different act from typing because nothing was offered, and it is worth
            # telling the writer about.
            used_free_text_when_offered_choices=bool(head and head.is_blocking and head.next_choices),
        )

        async with self.generation.lock(game_id):
            current = await self.games.get(game_id)
            if current is None:
                # Deleted underneath this request. Answering 202 with a null batch id
                # would tell the player their line was accepted, and the next poll would
                # 404 anyway.
                raise GameNotFound(game_id)
            current.history.append(f'{current.player.name} typed: "{text.strip()[:160]}"')
            current.played()
            current.style.record(kind=decision.kind, risk=intent.risk.value, target=intent.target)
            await self.games.save(current)

        batch = await self.generation.submit(game_id, intent, decision=decision)
        return batch, intent

    async def submit_choice(
        self, game_id: str, step_id: str, choice_id: str
    ) -> tuple[BatchState | None, PlayerIntent]:
        session = await self.get(game_id)
        if session.ended:
            raise InvalidAction("this game has ended")

        step = session.step_by_id(step_id)
        if step is None:
            raise InvalidAction(f"unknown step {step_id}")
        if not step.is_blocking:
            raise InvalidAction(f"step {step_id} is not a decision point")
        if step.index != session.cursor:
            raise InvalidAction("that decision point is no longer the current one")

        choice = next((c for c in step.next_choices if c.id == choice_id), None)
        if choice is None:
            raise InvalidAction(f"unknown choice {choice_id} on step {step_id}")

        intent = self.director.parse_keywords(session, choice.text)
        decision = DecisionContext(
            kind=DecisionKind.choice,
            step_id=step_id,
            chosen_text=choice.text,
            # The options they turned down are signal, not waste.
            rejected=[c.text for c in step.next_choices if c.id != choice_id],
        )

        async with self.generation.lock(game_id):
            current = await self.games.get(game_id)
            if current is None:
                raise GameNotFound(game_id)
            current.history.append(f'{current.player.name} chose: "{choice.text}"')
            current.played()
            current.style.record(kind=decision.kind, risk=intent.risk.value, target=intent.target)
            await self.games.save(current)

        batch = await self.generation.submit(
            game_id,
            intent,
            decision=decision,
            speculative_key=f"{game_id}:{step_id}:{choice_id}",
        )
        return batch, intent

    # -- views ---------------------------------------------------------------------------

    @staticmethod
    def to_state(session: GameSession) -> GameStateOut:
        return GameStateOut(
            game_id=session.id,
            world_id=session.world_id,
            player=session.player,
            world=session.world,
            characters=session.characters,
            current_step_index=session.cursor,
            queue_depth=session.queue_depth,
            awaiting_player=session.awaiting_player,
            ended=session.ended,
            pending=session.pending,
            recent_summary=session.history[-8:],
        )

    @staticmethod
    def to_save(session: GameSession) -> SaveGame:
        asset_ids = {
            ref.asset_id
            for step in session.steps
            for ref in (step.background_asset, step.character_asset)
            if ref and ref.asset_id
        }
        return SaveGame(
            game_id=session.id,
            world_id=session.world_id,
            current_step=session.cursor,
            story_arc=session.world.arc,
            world_state=session.world,
            character_states=session.characters,
            flags=session.world.flags,
            inventory=session.world.inventory,
            queue=[step.step_id for step in session.queued],
            asset_ids=sorted(asset_ids),
            memories=session.history[-20:],
            updated_at=session.updated_at,
        )
