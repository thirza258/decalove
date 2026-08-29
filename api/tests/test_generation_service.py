"""The background generation cycle — PRD §12, §25, §26.

Assembled directly from the pieces rather than driven over HTTP, so failure modes
that are hard to provoke through the API (a narrative agent that raises, a batch
that times out, a shutdown mid-generation) can be tested at all.
"""

from __future__ import annotations

import asyncio

import pytest

from app.agents.director import DirectorAgent
from app.agents.memory_agent import MemoryAgent
from app.agents.narrative import NarrativeAgent
from app.agents.safety import SafetyFilter
from app.agents.scripted import ScriptedNarrator
from app.agents.validator import Validator
from app.agents.visual import AssetSpec, VisualAgent
from app.assets.local_store import LocalAssetStore
from app.domain.enums import AssetStatus, BatchStatus, StepType
from app.domain.direction import DecisionContext, DecisionKind
from app.domain.intent import PlayerIntent
from app.domain.state import BatchState, CharacterState, GameSession, PlayerProfile, WorldState
from app.llm.embeddings import HashingEmbedding
from app.llm.placeholder_image import PlaceholderImageProvider
from app.repositories.memory_repo import (
    InMemoryAssetRepository,
    InMemoryGameRepository,
    InMemoryMemoryRepository,
)
from app.services.asset_service import AssetService
from app.services.game_service import GameService
from app.services.generation import GenerationService

INTENT = PlayerIntent(action="talk_to", target="aiko", raw="hi")
TYPED = DecisionContext(kind=DecisionKind.free_text, typed="hi")


class Engine:
    """A whole engine, in memory."""

    def __init__(self, world, tmp_path, *, images=False, speculative=0, chat=None):
        self.games = InMemoryGameRepository()
        self.memories = InMemoryMemoryRepository()
        self.assets_repo = InMemoryAssetRepository()

        validator = Validator(world=world, safety=SafetyFilter(), max_delta=5, max_steps=10)
        self.scripted = ScriptedNarrator(world)
        self.narrative = NarrativeAgent(world, validator, self.scripted, chat=chat, max_steps=10)
        self.visual = VisualAgent(world)
        self.memory = MemoryAgent(HashingEmbedding(), self.memories)
        self.assets = AssetService(
            self.assets_repo,
            LocalAssetStore(tmp_path),
            PlaceholderImageProvider(),
            enabled=images,
        )
        self.generation = GenerationService(
            games=self.games,
            narrative=self.narrative,
            director=DirectorAgent(world),
            memory=self.memory,
            visual=self.visual,
            assets=self.assets,
            timeout_s=5.0,
            speculative_branches=speculative,
        )
        self.service = GameService(
            world=world,
            games=self.games,
            director=DirectorAgent(world),
            narrative=self.narrative,
            memory=self.memory,
            visual=self.visual,
            assets=self.assets,
            generation=self.generation,
        )

    async def start(self, world):
        session = GameSession(
            id="g1",
            world_id=world.id,
            player=PlayerProfile(name="Kai"),
            world=WorldState(location="classroom", present_characters=["aiko", "ren"]),
            characters={
                c.id: CharacterState(id=c.id, name=c.name, relationship=dict(c.starting_relationship))
                for c in world.characters
            },
        )
        await self.games.create(session)
        return session


@pytest.fixture
async def engine(world, tmp_path):
    built = Engine(world, tmp_path)
    await built.start(world)
    yield built
    await built.generation.shutdown()


class TestSubmit:
    async def test_a_batch_appends_steps_and_marks_itself_ready(self, engine):
        batch = await engine.generation.submit("g1", INTENT, decision=TYPED)
        assert batch.status is BatchStatus.queued

        await engine.generation.drain()
        session = await engine.games.get("g1")

        assert session.steps, "nothing was generated"
        assert session.pending.status is BatchStatus.ready
        assert session.pending.step_count == len(session.steps)
        assert session.steps[-1].is_blocking
        assert session.history, "the run summary should be recorded for future prompts"

    async def test_steps_are_numbered_contiguously_across_batches(self, engine):
        for _ in range(3):
            await engine.generation.submit("g1", INTENT, decision=TYPED)
            await engine.generation.drain()
            # Clear pending so the next submit is not treated as a duplicate.
            session = await engine.games.get("g1")
            session.pending = None
            await engine.games.save(session)

        session = await engine.games.get("g1")
        assert [step.index for step in session.steps] == list(range(len(session.steps)))
        assert len({step.step_id for step in session.steps}) == len(session.steps)
        assert len({step.batch_id for step in session.steps}) == 3

    async def test_a_second_submit_while_one_is_running_is_a_no_op(self, engine, monkeypatch):
        original = engine.narrative.generate

        async def slow(*args, **kwargs):
            await asyncio.sleep(0.3)
            return await original(*args, **kwargs)

        monkeypatch.setattr(engine.narrative, "generate", slow)

        first = await engine.generation.submit("g1", INTENT, decision=TYPED)
        second = await engine.generation.submit("g1", INTENT, decision=TYPED)
        assert second.batch_id == first.batch_id, "a second turn must not queue a second batch"

        await engine.generation.drain()
        session = await engine.games.get("g1")
        assert session.pending.step_count == len(session.steps)

    async def test_an_unknown_game_is_not_submitted(self, engine):
        assert await engine.generation.submit("nope", INTENT, decision=TYPED) is None

    async def test_an_ended_game_is_not_submitted(self, engine):
        session = await engine.games.get("g1")
        session.ended = True
        await engine.games.save(session)
        assert await engine.generation.submit("g1", INTENT, decision=TYPED) is None


class TestFailureHandling:
    """PRD §26 — the game must never become unplayable because generation failed."""

    async def test_a_narrative_that_raises_still_produces_a_playable_run(self, engine, monkeypatch):
        async def explode(*args, **kwargs):
            raise RuntimeError("the model caught fire")

        monkeypatch.setattr(engine.narrative, "generate", explode)

        await engine.generation.submit("g1", INTENT, decision=TYPED)
        await engine.generation.drain()

        session = await engine.games.get("g1")
        assert session.steps, "the emergency fallback produced nothing"
        assert session.steps[-1].is_blocking
        assert session.pending.used_fallback is True
        assert session.pending.status is BatchStatus.ready

    async def test_a_timeout_falls_back_rather_than_hanging(self, engine, monkeypatch):
        engine.generation.timeout_s = 0.05

        async def forever(*args, **kwargs):
            await asyncio.sleep(30)

        monkeypatch.setattr(engine.narrative, "generate", forever)

        await engine.generation.submit("g1", INTENT, decision=TYPED)
        await asyncio.wait_for(engine.generation.drain(), timeout=10)

        session = await engine.games.get("g1")
        assert session.steps
        assert session.pending.used_fallback is True

    async def test_a_failed_commit_is_recorded_not_swallowed(self, engine, monkeypatch):
        from app.repositories.base import StaleSessionError

        async def conflict(*args, **kwargs):
            raise StaleSessionError("another writer got there first")

        monkeypatch.setattr(engine.generation, "commit_run", conflict)

        await engine.generation.submit("g1", INTENT, decision=TYPED)
        await engine.generation.drain()

        session = await engine.games.get("g1")
        assert session.pending.status is BatchStatus.failed
        assert "another writer" in session.pending.error


class TestLifecycle:
    async def test_shutdown_cancels_work_in_flight(self, world, tmp_path, monkeypatch):
        engine = Engine(world, tmp_path)
        await engine.start(world)

        async def forever(*args, **kwargs):
            await asyncio.sleep(60)

        monkeypatch.setattr(engine.narrative, "generate", forever)
        await engine.generation.submit("g1", INTENT, decision=TYPED)
        assert engine.generation._tasks

        await asyncio.wait_for(engine.generation.shutdown(), timeout=5)
        assert all(task.done() for task in engine.generation._tasks)

    async def test_drain_returns_immediately_when_nothing_is_running(self, engine):
        await asyncio.wait_for(engine.generation.drain(), timeout=2)

    async def test_locks_are_per_game(self, engine):
        assert engine.generation.lock("a") is engine.generation.lock("a")
        assert engine.generation.lock("a") is not engine.generation.lock("b")


class TestAssetWriteBack:
    async def test_art_generated_late_is_patched_into_undelivered_steps(self, world, tmp_path):
        """PRD §25 — story and images run concurrently, so art lands after the beats."""
        engine = Engine(world, tmp_path, images=True)
        await engine.start(world)

        await engine.generation.submit("g1", INTENT, decision=TYPED)
        await engine.generation.drain()

        session = await engine.games.get("g1")
        assert session.queue_depth > 0, "nothing was queued to patch"
        ready = [
            step
            for step in session.queued
            if step.background_asset and step.background_asset.status is AssetStatus.ready
        ]
        assert ready, "generated art never reached the undelivered steps"
        assert ready[0].background_asset.url
        await engine.generation.shutdown()

    async def test_one_asset_is_shared_by_every_beat_in_a_location(self, world, tmp_path):
        engine = Engine(world, tmp_path, images=True)
        await engine.start(world)
        await engine.generation.submit("g1", INTENT, decision=TYPED)
        await engine.generation.drain()

        session = await engine.games.get("g1")
        keys = {s.background_asset.cache_key for s in session.steps if s.background_asset}
        assert len(keys) == 1, f"a single-location run asked for {len(keys)} backgrounds"
        assert len(engine.assets_repo._by_key) <= 2  # background + one character sprite
        await engine.generation.shutdown()

    async def test_a_cached_asset_is_reused_rather_than_regenerated(self, world, tmp_path):
        """PRD §19."""
        engine = Engine(world, tmp_path, images=True)
        spec = AssetSpec(kind="background", cache_key="bg_fixed", prompt="a rooftop")

        first = await engine.assets.ensure(spec, world.id)
        second = await engine.assets.ensure(spec, world.id)

        assert first.asset_id == second.asset_id
        assert len(engine.assets_repo._by_id) == 1


class TestSpeculation:
    async def test_a_prefetched_branch_is_used_instead_of_regenerating(self, world, tmp_path):
        engine = Engine(world, tmp_path, speculative=2)
        await engine.start(world)

        await engine.generation.submit("g1", INTENT, decision=TYPED)
        await engine.generation.drain()

        session = await engine.games.get("g1")
        tail = session.steps[-1]
        assert tail.type is StepType.choice
        keys = sorted(
            k for k in engine.generation._speculative if k.startswith(f"g1:{tail.step_id}:")
        )
        assert len(keys) == 2, f"prefetch produced {len(keys)} branches, expected 2"

        chosen = keys[0]
        prepared = [step.narration for step in engine.generation._speculative[chosen][0].steps]
        delivered_before = len(session.steps)

        session.pending = None
        session.cursor = len(session.steps) - 1
        await engine.games.save(session)

        await engine.generation.submit("g1", INTENT, decision=TYPED, speculative_key=chosen)
        await engine.generation.drain()

        session = await engine.games.get("g1")
        appended = [step.narration for step in session.steps[delivered_before:]]
        assert appended == prepared, "the committed run is not the one that was prefetched"

        stale = [
            k for k in engine.generation._speculative if k.startswith(f"g1:{tail.step_id}:")
        ]
        assert stale == [], "branches for an answered decision point were not discarded"

        await engine.generation.shutdown()

    async def test_prefetch_is_off_by_default(self, engine):
        await engine.generation.submit("g1", INTENT, decision=TYPED)
        await engine.generation.drain()
        assert engine.generation._speculative == {}


class TestSpeculationIsolation:
    async def test_branches_are_keyed_per_game(self, world, tmp_path):
        """Step ids restart at step_00000 in every save. A key without the game id
        collides, and one player gets served a run pre-generated for another's story."""
        engine = Engine(world, tmp_path, speculative=2)
        await engine.start(world)

        engine.generation._speculative = {
            "game-a:step_00042:choice_1": ("A's branch", None),
            "game-b:step_00042:choice_1": ("B's branch", None),
        }

        taken = engine.generation._pop_speculation("game-b:step_00042:choice_1")

        assert taken[0] == "B's branch"
        assert "game-a:step_00042:choice_1" in engine.generation._speculative, (
            "answering one game's decision discarded another game's speculation"
        )
        await engine.generation.shutdown()

    async def test_forget_drops_a_deleted_game_s_branches(self, world, tmp_path):
        engine = Engine(world, tmp_path, speculative=2)
        await engine.start(world)
        engine.generation._speculative = {
            "doomed:step_00001:choice_1": ("x", None),
            "doomed:step_00001:choice_2": ("y", None),
            "survivor:step_00001:choice_1": ("z", None),
        }
        engine.generation.lock("doomed")

        engine.generation.forget("doomed")

        assert set(engine.generation._speculative) == {"survivor:step_00001:choice_1"}
        assert "doomed" not in engine.generation._locks
        await engine.generation.shutdown()

    async def test_celery_task_backend_dispatch(self, world, tmp_path, monkeypatch):
        """When TASK_QUEUE_BACKEND=celery, submit dispatches to Celery task queue."""
        calls = []

        class DummyTask:
            @staticmethod
            def delay(*args, **kwargs):
                calls.append((args, kwargs))

        monkeypatch.setattr("app.tasks.generation_tasks.generate_batch_task", DummyTask)

        engine = Engine(world, tmp_path)
        engine.generation.task_backend = "celery"
        session = await engine.start(world)

        batch = await engine.generation.submit(session.id, INTENT, decision=TYPED)
        assert batch is not None
        assert len(calls) == 1
        assert calls[0][0][0] == session.id
        await engine.generation.shutdown()
