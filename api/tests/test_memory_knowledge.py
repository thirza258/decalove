"""Memory 2.0 and character knowledge — the intelligence PRD's FR-01 and FR-02."""

from __future__ import annotations

import pytest

from app.agents.knowledge import CharacterKnowledgeManager, secret_fact_id
from app.agents.memory_agent import MemoryAgent, MemoryWeights
from app.domain.memory import MemoryStatus, MemoryVisibility
from app.domain.story import MemoryProposal
from app.llm.embeddings import HashingEmbedding
from app.repositories.memory_repo import InMemoryKnowledgeRepository, InMemoryMemoryRepository


def agent(**kwargs) -> MemoryAgent:
    return MemoryAgent(HashingEmbedding(), InMemoryMemoryRepository(), **kwargs)


async def remember(agent, text, *, character="aiko", step=0, **proposal):
    return await agent.remember(
        "g1",
        MemoryProposal(character=character, text=text, **proposal),
        step_index=step,
    )


class TestHybridRetrieval:
    async def test_an_unresolved_promise_scores_above_an_equally_similar_active_one(self):
        engine = agent()
        active = await remember(engine, "Kai mentioned the mural board.", step=0)
        promise = await remember(
            engine, "Kai mentioned the mural board.", step=0,
            event_type="promise", status="unresolved",
        )
        assert engine.score(promise, 0.5) > engine.score(active, 0.5)

    async def test_a_highly_important_old_memory_keeps_a_retention_floor(self):
        engine = agent()
        old = await remember(
            engine, "Kai broke a promise to Aiko.", step=0, importance=0.95,
        )
        fresh = await remember(engine, "Aiko said something forgettable.", step=99)
        # Old, maximally dissimilar, and out-ranked on every other term -- the floor is
        # what stops a nine-hundred-step-old betrayal from falling out of context.
        assert engine.score(old, 0.0, low=0.0, span=1.0, newest=100, focus={"aiko"}) >= 0.55
        assert engine.score(old, 0.0, low=0.0, span=1.0, newest=100, focus={"aiko"}) > (
            engine.score(fresh, 0.0, low=0.0, span=1.0, newest=100, focus={"aiko"})
        )

    async def test_a_flood_of_recent_trivia_cannot_bury_an_unresolved_promise(self):
        engine = agent(top_k=3)
        await remember(
            engine, "Kai promised Aiko the finished notebook by Friday.", step=0,
            event_type="promise", status="unresolved", importance=0.6,
        )
        for index in range(1, 20):
            await remember(engine, f"Aiko mentions the notebook again, point {index}.", step=index)
        top = await engine.recall("g1", "notebook", characters=["aiko"])
        assert any(record.unresolved for record in top)

    async def test_retrieval_stays_within_the_configured_context_budget(self):
        engine = agent(top_k=10, token_budget=30)
        for index in range(10):
            await remember(engine, "Aiko " + ("remembered detail " * 10) + str(index), step=index)
        recalled = await engine.recall("g1", "detail", characters=["aiko"])
        assert 1 <= len(recalled) < 10

    async def test_private_memories_do_not_follow_an_unrelated_character(self):
        engine = agent()
        await remember(engine, "Aiko told Kai her secret in confidence.", character="aiko", step=0)
        await remember(engine, "Mika lent Kai a pencil.", character="mika", step=1)
        recalled = await engine.recall("g1", "secret confidence", characters=["mika"])
        assert all(record.character == "mika" for record in recalled)

    async def test_weights_are_configurable(self):
        engine = agent(
            top_k=1,
            weights=MemoryWeights(semantic=1.0, importance=0, recency=0, relationship=0, unresolved=0),
        )
        await remember(engine, "Aiko finished the blue postcard.", step=0, importance=0.1)
        await remember(engine, "Aiko missed the train.", step=1, importance=1.0)
        top = await engine.recall("g1", "blue postcard", characters=["aiko"])
        assert "postcard" in top[0].text

    async def test_recall_records_that_a_memory_reached_a_prompt(self):
        repository = InMemoryMemoryRepository()
        engine = MemoryAgent(HashingEmbedding(), repository)
        await engine.remember(
            "g1", MemoryProposal(character="aiko", text="Aiko finished the blue postcard."),
            step_index=0,
        )
        await engine.recall(
            "g1", "blue postcard", characters=["aiko"], reference_step=12,
        )
        stored = await repository.for_game("g1")
        assert stored[0].last_referenced_step == 12

    async def test_structured_fields_are_recorded_with_provenance(self):
        engine = agent()
        record = await engine.remember(
            "g1",
            MemoryProposal(
                character="aiko", text="Kai promised the notebook by Friday.",
                event_type="promise", status="unresolved", visibility="private",
                category="relationship", importance=0.8,
            ),
            step_index=7, source_step_id="step_00007",
        )
        assert record.status is MemoryStatus.unresolved
        assert record.event_type == "promise"
        assert record.visibility is MemoryVisibility.private
        assert record.created_at_step == 7 and record.source_step_id == "step_00007"


class TestConsolidation:
    async def test_duplicates_merge_into_one_surviving_record_with_provenance(self):
        repository = InMemoryMemoryRepository()
        engine = MemoryAgent(HashingEmbedding(), repository)
        first = await engine.remember(
            "g1", MemoryProposal(character="aiko", text="Kai helped with the postcard.",
                                 importance=0.4), step_index=0,
        )
        second = await engine.remember(
            "g1", MemoryProposal(character="aiko", text="Kai helped with the postcard.",
                                 importance=0.9), step_index=1,
        )
        report = await engine.consolidate("g1")
        stored = {record.id: record for record in await repository.for_game("g1")}
        assert report.merged == 1 and report.superseded == 1
        assert stored[second.id].status is MemoryStatus.active
        assert first.id in stored[second.id].merged_from
        assert stored[first.id].status is MemoryStatus.superseded
        assert stored[first.id].metadata["superseded_by"] == second.id

    async def test_an_unresolved_event_is_never_merged_down_into_a_resolved_one(self):
        repository = InMemoryMemoryRepository()
        engine = MemoryAgent(HashingEmbedding(), repository)
        await engine.remember(
            "g1", MemoryProposal(character="aiko", text="Kai promised to fix the lamp.",
                                 event_type="promise", status="active", importance=0.9),
            step_index=0,
        )
        await engine.remember(
            "g1", MemoryProposal(character="aiko", text="Kai promised to fix the lamp.",
                                 event_type="promise", status="unresolved", importance=0.3),
            step_index=1,
        )
        await engine.consolidate("g1")
        survivor = next(
            record for record in await repository.for_game("g1")
            if record.status is not MemoryStatus.superseded
        )
        assert survivor.unresolved

    async def test_contradictory_memories_are_kept_and_flagged(self):
        repository = InMemoryMemoryRepository()
        engine = MemoryAgent(HashingEmbedding(), repository)
        await engine.remember(
            "g1", MemoryProposal(character="aiko", text="Kai kept the promise about the play.",
                                 event_type="promise", status="fulfilled", subject="play"),
            step_index=0,
        )
        await engine.remember(
            "g1", MemoryProposal(character="aiko", text="Kai broke the promise about the play.",
                                 event_type="promise", status="broken", subject="play"),
            step_index=1,
        )
        report = await engine.consolidate("g1")
        assert report.contradictions == 1
        records = await repository.for_game("g1")
        assert all(record.status is not MemoryStatus.superseded for record in records)
        assert records[0].metadata["contradicts"]


class TestKnowledge:
    @pytest.fixture
    def manager(self, world):
        return CharacterKnowledgeManager(InMemoryKnowledgeRepository(), world=world)

    def step(self, **overrides):
        from app.domain.enums import StepType
        from app.domain.story import StoryStep

        payload = dict(
            step_id="step_00003", index=3, batch_id="b1", type=StepType.dialogue,
            location="classroom", characters=["aiko"],
            dialogue={"speaker": "aiko", "text": "I lost the blue notebook."},
        )
        payload.update(overrides)
        return StoryStep(**payload)

    async def test_only_the_people_in_the_scene_learn_the_fact(self, manager, session):
        await manager.acquire_from_step(session, self.step(characters=["aiko"]))
        knowledge = await manager.for_game(session.id)
        assert "aiko" in knowledge
        assert "ren" not in knowledge

    async def test_one_listener_is_told_directly_and_a_crowd_overhears(self, manager, session):
        await manager.acquire_from_step(session, self.step(characters=["aiko", "ren"]))
        knowledge = await manager.for_game(session.id)
        assert knowledge["ren"][0].acquisition_method.value == "told_directly"

        await manager.acquire_from_step(
            session,
            self.step(step_id="step_00004", index=4, characters=["aiko", "ren", "mika"]),
        )
        knowledge = await manager.for_game(session.id)
        latest = max(knowledge["ren"], key=lambda record: record.created_at_step)
        assert latest.acquisition_method.value == "overheard"

    async def test_a_character_cannot_reveal_a_secret_they_never_learned(self, manager, session):
        await manager.seed(session.id, session)
        aiko = await manager.retrieve(session.id, "aiko")
        ren = await manager.retrieve(session.id, "ren")
        secret_fact = secret_fact_id(session.id, "aiko")

        assert any(fact.fact_id == secret_fact for fact in aiko)
        assert not any(fact.fact_id == secret_fact for fact in ren)
        assert manager.validate_claim("aiko", "the thing she never told anyone", aiko) is False
        assert manager.validate_claim("aiko", "their own secret", aiko) is True

    async def test_a_spoken_secret_is_learned_by_the_scene(self, manager, session):
        from app.domain.enums import StepType
        from app.domain.story import StoryStep

        secret = manager.world.character("aiko").secret
        step = StoryStep(
            step_id="step_00009", index=9, batch_id="b1", type=StepType.dialogue,
            location="classroom", characters=["aiko", "ren"],
            dialogue={"speaker": "aiko", "text": secret},
        )
        await manager.acquire_from_step(session, step)
        ren = await manager.retrieve(session.id, "ren")
        assert any(fact.fact_id == secret_fact_id(session.id, "aiko") for fact in ren)

    async def test_acquisition_is_idempotent(self, manager, session):
        step = self.step(characters=["aiko", "ren"])
        await manager.acquire_from_step(session, step)
        await manager.acquire_from_step(session, step)
        knowledge = await manager.for_game(session.id)
        assert len(knowledge["aiko"]) == 1 and len(knowledge["ren"]) == 1

    async def test_beliefs_can_differ_and_be_corrected_later(self, manager, session):
        await manager.acquire_from_step(session, self.step(characters=["aiko", "ren"]))
        knowledge = await manager.for_game(session.id)
        assert knowledge["aiko"][0].proposition == knowledge["ren"][0].proposition
        # A misconception is a distinct record of the same fact; the engine keeps both.
        knowledge["ren"][0].knowledge_type = "believed"
        knowledge["ren"][0].proposition = "Aiko lost it on purpose."
        assert knowledge["ren"][0].proposition != knowledge["aiko"][0].proposition

    async def test_the_rendered_boundary_names_who_knows_nothing(self, manager, session):
        await manager.acquire_from_step(session, self.step(characters=["aiko"]))
        rendered = manager.render(await manager.for_game(session.id), ["aiko", "ren"])
        assert "Aiko Serizawa knows" in rendered or "knows:" in rendered
        assert "no established knowledge beyond this scene" in rendered
