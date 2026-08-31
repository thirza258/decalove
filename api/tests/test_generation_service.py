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

    async def test_the_sampling_gate_is_rolled_before_anything_is_queued(self, world, tmp_path):
        """A skipped image must not cost a queue slot to discover.

        Gating inside the worker meant nineteen of every twenty jobs (the 5% default) were
        routed to the GPU worker and given a whole runtime purely to decide to do nothing,
        in front of the ones that were going to draw something.
        """
        engine = Engine(world, tmp_path, images=True)
        engine.assets.generation_probability = 0.0

        # The hand-off both backends share: commit_run either dispatches this to the image
        # queue or spawns it in-process, and the gate has to be upstream of that choice.
        handed_off = []
        original = engine.generation._fill_assets

        async def spy(game_id, specs):
            handed_off.append(specs)
            await original(game_id, specs)

        engine.generation._fill_assets = spy

        await engine.start(world)
        await engine.generation.submit("g1", INTENT, decision=TYPED)
        await engine.generation.drain()

        assert handed_off == [], "an image the gate was going to skip was still handed to a worker"
        assert engine.assets_repo._by_id == {}
        await engine.generation.shutdown()

    async def test_the_seed_and_negatives_survive_the_trip_to_the_image_worker(
        self, world, tmp_path
    ):
        """A field added to AssetSpec must not be a field silently dropped on dispatch.

        The payload used to be hand-listed, which would have left images seeded and
        negated in-process and neither under Celery -- i.e. exactly the deployment that
        generates them, and a downgrade nothing would have reported.
        """
        from app.agents.visual import AssetSpec

        engine = Engine(world, tmp_path, images=True)
        await engine.start(world)
        await engine.generation.submit("g1", INTENT, decision=TYPED)
        await engine.generation.drain()

        session = await engine.games.get("g1")
        specs = [
            spec
            for step in session.steps
            for spec in engine.visual.specs_for(step.visual)
            if step.visual
        ]
        assert specs, "the run produced no asset specs to check"

        for spec in specs:
            # Exactly the round trip generation.py and the worker perform.
            assert AssetSpec.from_payload(spec.to_payload()) == spec
            assert spec.seed is not None, f"{spec.cache_key} has no seed"
            assert spec.negative, f"{spec.cache_key} has no negatives"
        await engine.generation.shutdown()

    async def test_art_that_loses_a_write_race_is_retried_not_dropped(self, world, tmp_path):
        """The per-game lock is process-local, so once the image worker is its own process
        nothing serialises this against a concurrent save. Dropping the conflict would mean
        art that was generated, stored and paid for is never shown to anybody.
        """
        from app.domain.story import AssetRef
        from app.repositories.base import StaleSessionError

        engine = Engine(world, tmp_path, images=True)
        await engine.start(world)
        await engine.generation.submit("g1", INTENT, decision=TYPED)
        await engine.generation.drain()

        session = await engine.games.get("g1")
        target = next(s for s in session.steps if s.background_asset)
        cache_key = target.background_asset.cache_key
        # Undeliver the step and blank its reference, so there is something to patch.
        session.cursor = -1
        session.steps[target.index] = target.model_copy(
            update={"background_asset": AssetRef(cache_key=cache_key, status=AssetStatus.pending)}
        )
        await engine.games.save(session)

        original = engine.games.save
        rejections = 2

        async def reject_then_accept(saved):
            nonlocal rejections
            if rejections:
                rejections -= 1
                raise StaleSessionError("another writer got there first")
            await original(saved)

        engine.games.save = reject_then_accept
        await engine.generation._patch_assets(
            "g1", {cache_key: AssetRef(cache_key=cache_key, status=AssetStatus.ready, asset_id="a1")}
        )
        engine.games.save = original

        assert rejections == 0, "the patch gave up instead of retrying"
        session = await engine.games.get("g1")
        patched = session.steps[target.index].background_asset
        assert patched.status is AssetStatus.ready
        assert patched.asset_id == "a1"
        await engine.generation.shutdown()


class TestIntentRefinement:
    """Typed input is keyword-parsed on the request and re-read by the model in the worker.

    The parse used to run inline, holding the player's client on a blocking POST for a
    model round-trip whose result the Ren'Py client then discards.
    """

    async def test_the_worker_upgrades_a_keyword_intent(self, world, tmp_path):
        seen = []

        class RefiningDirector(DirectorAgent):
            async def parse(self, session, raw):
                seen.append(raw)
                return PlayerIntent(action="confess", target="rin", risk="high", raw=raw)

        engine = Engine(world, tmp_path)
        engine.generation.director = RefiningDirector(world)
        await engine.start(world)

        await engine.generation.submit(
            "g1", INTENT, decision=TYPED, refine_input="I tell Rin how I feel"
        )
        await engine.generation.drain()

        assert seen == ["I tell Rin how I feel"]
        session = await engine.games.get("g1")
        assert session.last_intent.action == "confess"
        assert session.last_intent.target == "rin"
        await engine.generation.shutdown()

    async def test_style_is_graded_on_the_refined_intent_not_the_keyword_one(
        self, world, tmp_path
    ):
        """PlayerStyle.targets is what picks the ending (agents/ending.py). Recording the
        placeholder intent at request time would quietly change who the player ends up with.
        """

        class RefiningDirector(DirectorAgent):
            async def parse(self, session, raw):
                return PlayerIntent(action="confess", target="rin", risk="high", raw=raw)

        engine = Engine(world, tmp_path)
        engine.generation.director = RefiningDirector(world)
        await engine.start(world)

        # INTENT is the keyword parse: talk_to / aiko / low risk.
        await engine.generation.submit("g1", INTENT, decision=TYPED, refine_input="I tell Rin")
        await engine.generation.drain()

        style = (await engine.games.get("g1")).style
        assert style.favourite == "rin", f"style followed the keyword parse: {style.targets}"
        assert style.bold == 1 and style.cautious == 0
        assert style.typed == 1
        await engine.generation.shutdown()

    async def test_a_failed_refinement_keeps_the_keyword_intent(self, world, tmp_path):
        from app.llm.base import LLMError

        class BrokenDirector(DirectorAgent):
            async def parse(self, session, raw):
                raise LLMError("upstream is down")

        engine = Engine(world, tmp_path)
        engine.generation.director = BrokenDirector(world)
        await engine.start(world)

        await engine.generation.submit("g1", INTENT, decision=TYPED, refine_input="hi")
        await engine.generation.drain()

        session = await engine.games.get("g1")
        assert session.last_intent.action == INTENT.action
        assert session.pending.status is BatchStatus.ready, "a bad parse cost the player a turn"
        await engine.generation.shutdown()


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

        batch = await engine.generation.submit(
            session.id, INTENT, decision=TYPED, refine_input="I say hello"
        )
        assert batch is not None
        assert len(calls) == 1
        # Dispatched by keyword: the task signature has grown twice now, and a positional
        # payload silently shifts every argument when it grows again.
        payload = calls[0][1]
        assert payload["game_id"] == session.id
        assert payload["batch_id"] == batch.batch_id
        assert payload["refine_input"] == "I say hello"
        await engine.generation.shutdown()

    async def test_story_and_images_are_dispatched_to_separate_queues(self):
        """The whole point of the split: a GPU pass must never be in front of a player's
        next line. One shared queue plus worker_prefetch_multiplier=1 means exactly that.
        """
        celery = pytest.importorskip("app.tasks.celery_app")
        if celery.celery_app is None:
            pytest.skip("celery is not installed")

        routes = celery.celery_app.conf.task_routes
        story = routes["app.tasks.generation_tasks.generate_batch_task"]["queue"]
        images = routes["app.tasks.generation_tasks.generate_assets_task"]["queue"]

        assert story == celery.STORY_QUEUE
        assert images == celery.IMAGE_QUEUE
        assert story != images
        # Unrouted work is story work, never the queue with the GPU behind it.
        assert celery.celery_app.conf.task_default_queue == celery.STORY_QUEUE
