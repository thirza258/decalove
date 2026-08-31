"""Background story generation — PRD §12, §14, §25.

``submit()`` returns immediately; the HTTP handler never waits on a model. Where the work
then runs is a deployment choice (``TASK_QUEUE_BACKEND``): in-process ``asyncio`` tasks so
a single-node MVP needs no second service, or Celery so it can be scaled out. Everything
that would make a queue necessary is behind this class either way.

Under Celery the two halves of a turn go to *different* queues and different workers.
Story generation is an API call measured in seconds and images are a GPU pass measured in
minutes; on one queue the images head-of-line block the prose. See ``tasks/celery_app.py``.

Concurrency: every mutation of a session is serialised by a per-game lock, and the slow
part (the model call) happens *outside* the lock, so delivering steps to the player is
never blocked by generating the next batch. That lock is process-local, so anything that
can race a worker against the API -- ``_patch_assets`` -- has to handle losing.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from app.agents.director import DirectorAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.narrative import NarrativeAgent, RunResult
from app.agents.visual import AssetSpec, VisualAgent
from app.domain.direction import DecisionContext, DecisionKind, Directive
from app.domain.enums import AssetStatus, BatchStatus, StepType
from app.domain.intent import PlayerIntent
from app.domain.state import BatchState, GameSession
from app.domain.story import AssetRef, StoryStep
from app.repositories.base import GameRepository, StaleSessionError
from app.services.asset_service import AssetService

log = logging.getLogger(__name__)

#: Tries at writing generated art back into a session before giving up. More than one
#: because the per-game lock below is process-local: with the API and the Celery workers
#: in separate processes, nothing serialises this against a concurrent save.
ASSET_PATCH_ATTEMPTS = 3

#: Ceiling on the worker-side intent refinement. The chat client's own timeout is the full
#: generation budget, which is far too long to spend on a 400-token parse -- if the model
#: is that slow, the keyword intent the handler already produced is the better answer.
INTENT_REFINE_TIMEOUT_S = 20.0


class GenerationService:
    def __init__(
        self,
        *,
        games: GameRepository,
        narrative: NarrativeAgent,
        director: DirectorAgent,
        memory: MemoryAgent,
        visual: VisualAgent,
        assets: AssetService,
        timeout_s: float = 120.0,
        speculative_branches: int = 0,
        task_backend: str = "asyncio",
    ) -> None:
        self.games = games
        self.narrative = narrative
        self.director = director
        self.memory = memory
        self.visual = visual
        self.assets = assets
        self.timeout_s = timeout_s
        self.speculative_branches = speculative_branches
        self.task_backend = task_backend

        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        #: Pre-generated branches keyed by ``f"{game_id}:{step_id}:{choice_id}"``. The game
        #: id is load-bearing: step ids restart at ``step_00000`` in every save, so a
        #: key without it collides across games and one player could be served a run
        #: pre-generated for somebody else's story.
        #: In-process only: a lost speculation costs one regeneration, never correctness.
        self._speculative: dict[str, tuple[RunResult, Directive]] = {}

    # -- locking -------------------------------------------------------------------------

    def lock(self, game_id: str) -> asyncio.Lock:
        lock = self._locks.get(game_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[game_id] = lock
        return lock

    def forget(self, game_id: str) -> None:
        """Drop a deleted game's lock and any speculation held for it.

        Without this the lock table is a slow memory leak keyed by every game id the
        process has ever seen -- which garbage collection would otherwise make worse, not
        better.
        """
        self._locks.pop(game_id, None)
        for key in [k for k in self._speculative if k.startswith(f"{game_id}:")]:
            del self._speculative[key]

    # -- lifecycle -----------------------------------------------------------------------

    def _spawn(self, coro) -> asyncio.Task[None]:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def drain(self, timeout: float = 30.0) -> None:
        """Wait for in-flight generation. Used by tests and by graceful shutdown."""
        while self._tasks:
            pending = list(self._tasks)
            done, _ = await asyncio.wait(pending, timeout=timeout)
            if not done:
                break

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    # -- submission ----------------------------------------------------------------------

    async def submit(
        self,
        game_id: str,
        intent: PlayerIntent,
        *,
        decision: DecisionContext,
        speculative_key: str | None = None,
        refine_input: str | None = None,
    ) -> BatchState | None:
        """Queue one generation cycle. Returns the batch, or ``None`` if one is already running.

        ``refine_input`` is the player's raw text when the caller handed over a keyword
        intent and wants the model's reading of it. Parsed here rather than in the handler
        so the 202 goes out without waiting on a model.
        """
        async with self.lock(game_id):
            session = await self.games.get(game_id)
            if session is None or session.ended:
                return None
            if session.pending and session.pending.status in (BatchStatus.queued, BatchStatus.running):
                return session.pending
            if any(step.is_ending for step in session.queued):
                # The finale is written and waiting to be read. Accepting another turn here
                # would generate a second ending nobody will ever see.
                log.info("refusing a new batch for %s: the ending is already queued", game_id)
                return None

            batch = BatchState(
                batch_id=uuid.uuid4().hex,
                status=BatchStatus.queued,
                source=decision.kind.value,
            )
            session.pending = batch
            session.last_intent = intent
            await self.games.save(session)
            snapshot = session

        prepared = self._pop_speculation(speculative_key)
        if self.task_backend == "celery":
            try:
                from app.tasks.generation_tasks import generate_batch_task
                generate_batch_task.delay(
                    game_id=game_id,
                    batch_id=batch.batch_id,
                    intent_dict=intent.model_dump(),
                    decision_dict=decision.model_dump(),
                    speculative_key=speculative_key,
                    refine_input=refine_input,
                )
            except Exception:
                log.warning("failed to dispatch batch to Celery, falling back to in-process async", exc_info=True)
                self._spawn(
                    self._run_batch(
                        game_id, batch, intent, decision, snapshot, prepared, refine_input
                    )
                )
        else:
            self._spawn(
                self._run_batch(game_id, batch, intent, decision, snapshot, prepared, refine_input)
            )
        return batch

    def _pop_speculation(self, key: str | None) -> tuple[RunResult, Directive] | None:
        """Take the branch the player chose and discard the ones they did not.

        Without the discard, every unchosen branch stays in memory for the life of the
        process -- the player only ever comes back through one of them.
        """
        if not key:
            return None
        prepared = self._speculative.pop(key, None)
        prefix = key.split(":", 1)[0] + ":"
        for sibling in [k for k in self._speculative if k.startswith(prefix)]:
            del self._speculative[sibling]
        return prepared

    # -- the cycle -----------------------------------------------------------------------

    async def _run_batch(
        self,
        game_id: str,
        batch: BatchState,
        intent: PlayerIntent,
        decision: DecisionContext,
        snapshot: GameSession,
        prepared: tuple[RunResult, Directive] | None,
        refine_input: str | None = None,
    ) -> None:
        batch.status = BatchStatus.running
        record_style: DecisionKind | None = None
        if refine_input:
            intent = await self._refine_intent(snapshot, intent, refine_input)
            # The handler deliberately did not record this turn's style: the keyword intent
            # it had was a placeholder, and PlayerStyle.targets is what picks the ending
            # (agents/ending.py). Record it here, from the intent the run is written to.
            record_style = decision.kind
        directive = self.director.plan(
            snapshot, intent, decision, max_steps=self.narrative.max_steps
        )
        try:
            if prepared is not None:
                result, directive = prepared
            else:
                result = await asyncio.wait_for(
                    self._generate(snapshot, intent, decision, directive), timeout=self.timeout_s
                )
        except asyncio.TimeoutError:
            log.warning("generation for %s timed out after %.0fs", game_id, self.timeout_s)
            result = self._scripted(snapshot, intent, directive)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the game must survive any generator failure
            log.exception("generation for %s failed unexpectedly", game_id)
            result = self._scripted(snapshot, intent, directive)

        try:
            await self.commit_run(game_id, batch, result, intent, directive, record_style=record_style)
        except StaleSessionError as exc:
            log.error("could not commit batch %s for %s: %s", batch.batch_id, game_id, exc)
            await self._mark_failed(game_id, batch, str(exc))
            return

        if self.speculative_branches > 0:
            self._spawn(self._speculate(game_id))

    async def _refine_intent(
        self, snapshot: GameSession, intent: PlayerIntent, raw: str
    ) -> PlayerIntent:
        """Ask the model what the player meant, having already answered them.

        The keyword parse in ``GameService.submit_action`` is good enough to commit to;
        this is the upgrade, and it belongs here because the player is no longer waiting
        on the request that produced it.
        """
        try:
            return await asyncio.wait_for(
                self.director.parse(snapshot, raw), timeout=INTENT_REFINE_TIMEOUT_S
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a worse intent is never worth losing a turn over
            log.warning(
                "intent refinement for %s failed; keeping the keyword parse",
                snapshot.id,
                exc_info=True,
            )
            return intent

    async def _generate(
        self,
        snapshot: GameSession,
        intent: PlayerIntent,
        decision: DecisionContext,
        directive: Directive,
    ) -> RunResult:
        # Retrieval follows the Director's focus rather than the raw intent: the run is
        # about whoever is carrying it, which is not always who was addressed.
        focus = directive.focus or list(snapshot.world.present_characters)
        query = (
            " ".join(
                filter(None, [intent.summary, intent.raw, decision.chosen_text, decision.typed])
            )
            or intent.action
        )
        memories = await self.memory.recall(snapshot.id, query, characters=focus)
        return await self.narrative.generate(
            snapshot, intent, memories, decision=decision, directive=directive
        )

    def _scripted(
        self, snapshot: GameSession, intent: PlayerIntent, directive: Directive | None = None
    ) -> RunResult:
        # The finale has to survive this path too: a timeout on the very last run would
        # otherwise hand the player another decision and the story would never end.
        run = (
            self.narrative.scripted.finale(snapshot, directive)
            if directive is not None and directive.is_finale
            else self.narrative.scripted.run(
                snapshot, intent, max_steps=self.narrative.max_steps, directive=directive
            )
        )
        report = self.narrative.validator.validate(
            run, snapshot, allow_ending=bool(directive and directive.is_finale)
        )
        return RunResult(
            steps=report.steps,
            summary=run.summary,
            used_fallback=True,
            provider="scripted-emergency",
            report=report,
        )

    async def commit_run(
        self,
        game_id: str,
        batch: BatchState,
        result: RunResult,
        intent: PlayerIntent,
        directive: Directive | None = None,
        *,
        record_style: DecisionKind | None = None,
    ) -> None:
        """Append a run to the ledger and start generating any art it needs.

        The single commit path. The authored opening goes through it too -- when it did
        not, the opening scene's backgrounds were never requested, so a player who only
        saw the first scene never got any generated art at all.
        """
        misses = await self._commit(game_id, batch, result, intent, directive, record_style=record_style)
        # Rolled here, not in the worker. At the default 5% probability, gating downstream
        # meant nineteen of every twenty image jobs were queued, routed to the GPU worker
        # and given a whole runtime just to decide to do nothing -- ahead of the ones that
        # were going to draw something.
        misses = [spec for spec in misses if self.assets.wants_generation(spec)]
        if misses:
            if self.task_backend == "celery":
                try:
                    from app.tasks.generation_tasks import generate_assets_task
                    session = await self.games.get(game_id)
                    world_id = session.world_id if session else ""
                    generate_assets_task.delay(
                        game_id,
                        [
                            {"kind": s.kind, "cache_key": s.cache_key, "prompt": s.prompt}
                            for s in misses
                        ],
                        world_id,
                    )
                except Exception:
                    log.warning("failed to dispatch asset generation to Celery, falling back", exc_info=True)
                    self._spawn(self._fill_assets(game_id, misses))
            else:
                self._spawn(self._fill_assets(game_id, misses))

    async def _commit(
        self,
        game_id: str,
        batch: BatchState,
        result: RunResult,
        intent: PlayerIntent,
        directive: Directive | None = None,
        *,
        record_style: DecisionKind | None = None,
    ) -> list[AssetSpec]:
        """Append the run to the ledger under the lock, and report uncached art."""
        misses: list[AssetSpec] = []
        async with self.lock(game_id):
            session = await self.games.get(game_id)
            if session is None:
                return []
            if session.ended:
                log.info("discarding batch %s: %s has already ended", batch.batch_id, game_id)
                return []

            base = len(session.steps)
            for offset, generated in enumerate(result.steps):
                spec = self.visual.normalise(generated, session)
                generated.visual = spec

                if generated.type is StepType.ending and directive is not None:
                    # Engine-written, never model-written: the validator strips these keys
                    # from anything the model proposes, so this is the only place the
                    # marker that says "the story is over" can come from.
                    generated.flags_set = {
                        **generated.flags_set,
                        "ending": directive.ending_kind or "solo",
                        "ending_partner": directive.ending_partner or "",
                    }
                background = self.visual.background_spec(spec)
                character = self.visual.character_spec(spec)
                background_ref = await self.assets.reference(background) if background else None
                character_ref = await self.assets.reference(character) if character else None
                if background and background_ref.status is AssetStatus.pending:
                    misses.append(background)
                if character and character_ref.status is AssetStatus.pending:
                    misses.append(character)

                session.steps.append(
                    StoryStep(
                        **generated.model_dump(),
                        step_id=f"step_{base + offset:05d}",
                        index=base + offset,
                        batch_id=batch.batch_id,
                        fallback=result.used_fallback,
                        background_asset=background_ref,
                        character_asset=character_ref,
                    )
                )

            if result.summary:
                session.history.append(result.summary)
            session.last_intent = intent
            if record_style is not None:
                session.style.record(
                    kind=record_style, risk=intent.risk.value, target=intent.target
                )
            if directive is not None:
                # Read back when planning the next run, so pacing has memory.
                session.last_directive = directive
            session.pending = BatchState(
                batch_id=batch.batch_id,
                status=BatchStatus.ready,
                source=batch.source,
                step_count=len(result.steps),
                used_fallback=result.used_fallback,
                created_at=batch.created_at,
            )
            await self.games.save(session)

        # De-duplicate: one batch usually reuses the same background across every beat.
        unique: dict[str, AssetSpec] = {spec.cache_key: spec for spec in misses}
        return list(unique.values())

    async def _mark_failed(self, game_id: str, batch: BatchState, error: str) -> None:
        async with self.lock(game_id):
            session = await self.games.get(game_id)
            if session is None:
                return
            session.pending = BatchState(
                batch_id=batch.batch_id,
                status=BatchStatus.failed,
                source=batch.source,
                error=error,
                created_at=batch.created_at,
            )
            with contextlib.suppress(StaleSessionError):
                await self.games.save(session)

    # -- images --------------------------------------------------------------------------

    async def _fill_assets(self, game_id: str, specs: list[AssetSpec]) -> None:
        """Generate missing art, then patch it into steps the player has not reached yet."""
        session = await self.games.get(game_id)
        world_id = session.world_id if session else ""
        refs: dict[str, AssetRef] = {}
        for spec in specs:
            # gated=False: commit_run already rolled the sampling gate for these specs, and
            # rolling it again here would square the probability.
            ref = await self.assets.ensure(spec, world_id, gated=False)
            if ref.status is AssetStatus.ready:
                refs[spec.cache_key] = ref
        if not refs:
            return
        await self._patch_assets(game_id, refs)

    async def _patch_assets(self, game_id: str, refs: dict[str, AssetRef]) -> None:
        """Write ready asset references into steps the player has not reached yet.

        Retried rather than suppressed. The per-game lock is process-local, so once the
        image worker is a separate process from the API (which is the point of the split)
        nothing serialises this against a concurrent save -- and dropping the conflict
        would mean art that was generated, paid for and stored is never shown to anybody.
        """
        for attempt in range(1, ASSET_PATCH_ATTEMPTS + 1):
            async with self.lock(game_id):
                # Re-read every attempt: the retry has to be applied to whatever the other
                # writer left behind, not to the stale copy that lost the race.
                session = await self.games.get(game_id)
                if session is None:
                    return
                patched = 0
                # Index into session.steps, not session.queued: queued is a fresh slice, so a
                # replacement written there would be discarded. Steps are frozen, so this is a
                # copy-and-replace rather than an in-place edit.
                for position in range(session.cursor + 1, len(session.steps)):
                    step = session.steps[position]
                    updates = {}
                    for attribute in ("background_asset", "character_asset"):
                        current = getattr(step, attribute)
                        if current and current.status is not AssetStatus.ready and current.cache_key in refs:
                            updates[attribute] = refs[current.cache_key]
                    if updates:
                        session.steps[position] = step.model_copy(update=updates)
                        patched += len(updates)
                if not patched:
                    # Nothing left to patch: the player has already read past every step
                    # that wanted this art, or another writer got there first.
                    return
                try:
                    await self.games.save(session)
                except StaleSessionError as exc:
                    log.info(
                        "asset patch for %s lost a write race (attempt %d/%d): %s",
                        game_id, attempt, ASSET_PATCH_ATTEMPTS, exc,
                    )
                    continue
                log.info("patched %d asset reference(s) into undelivered steps of %s", patched, game_id)
                return

        log.warning(
            "gave up patching asset references into %s after %d attempts; the art is stored "
            "and will be picked up by the next batch that references the same cache key",
            game_id, ASSET_PATCH_ATTEMPTS,
        )

    # -- speculation ---------------------------------------------------------------------

    async def _speculate(self, game_id: str) -> None:
        """Pre-generate a run per branch so a choice resolves instantly.

        Off by default (``SPECULATIVE_PREFETCH_MAX_BRANCHES=0``): it costs one model call
        per option, and all but one of them is thrown away.
        """
        session = await self.games.get(game_id)
        if session is None or not session.steps:
            return
        tail = session.steps[-1]
        if tail.type is not StepType.choice:
            return

        for choice in tail.next_choices[: self.speculative_branches]:
            key = f"{game_id}:{tail.step_id}:{choice.id}"
            if key in self._speculative:
                continue
            intent = self.director.parse_keywords(session, choice.text)
            decision = DecisionContext(
                kind=DecisionKind.choice,
                step_id=tail.step_id,
                chosen_text=choice.text,
                rejected=[c.text for c in tail.next_choices if c.id != choice.id],
            )
            directive = self.director.plan(
                session, intent, decision, max_steps=self.narrative.max_steps
            )
            try:
                self._speculative[key] = (
                    await self._generate(session, intent, decision, directive),
                    directive,
                )
            except Exception:  # noqa: BLE001 - speculation is best-effort by definition
                log.debug("speculative branch %s failed", key, exc_info=True)
