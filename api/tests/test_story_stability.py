"""Regressions for choice boundaries, chapter continuity, endings and memory outages."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.agents.memory_agent import MemoryAgent
from app.agents.narrative import NarrativeAgent
from app.agents.prompts import build_context, build_run_prompt, build_system_prompt
from app.domain.direction import Directive
from app.domain.enums import StepType
from app.domain.intent import PlayerIntent
from app.domain.story import GeneratedRun, GeneratedStep, MemoryProposal, RelationshipDelta, StoryStep
from app.llm.embeddings import HashingEmbedding
from app.repositories.base import StaleSessionError
from app.repositories.memory_repo import InMemoryMemoryRepository
from test_generation_service import Engine, INTENT, TYPED
from test_llm_path import StubChat, step as llm_step, choice_step as llm_choice


def beat(**kwargs):
    return GeneratedStep(**{
        "type": "narration", "location": "classroom", "characters": ["aiko"],
        "narration": "Aiko holds the blue notebook open.", **kwargs,
    })


def question():
    return beat(type="choice", narration="Aiko waits for an answer.", next_choices=[
        {"id": "yes", "text": "Offer to help with one page."},
        {"id": "ask", "text": "Ask what the notebook is for."},
        {"id": "no", "text": "Say you cannot help today."},
    ])


def story_step(index, **kwargs):
    return StoryStep(**beat(**kwargs).model_dump(), step_id=f"step_{index:05d}", index=index, batch_id="b")


def test_authored_opening_tail_matches_both_clients(narrator, validator, session):
    root = Path(__file__).resolve().parents[2]
    clients = [(root / path).read_text() for path in (
        "frontend/src/game/opening.ts", "game/decalove/60_static_opening.rpy",
    )]
    report = validator.validate(narrator.opening(session), session, is_opening=True)
    assert len(report.steps) == 20 and report.steps[14].is_blocking
    for tail in report.steps[15:]:
        assert tail.location == "library" and tail.type is StepType.narration
        assert not tail.relationship_changes and not tail.flags_set and not tail.memory
        assert all(tail.narration in source for source in clients)


@pytest.mark.parametrize("closing_type", ["narration", "ending"])
def test_finale_has_no_unanswerable_menu_anywhere(validator, session, closing_type):
    result = validator.validate(GeneratedRun(steps=[
        beat(), question(), beat(narration="The notebook closes.", type=closing_type),
    ]), session, allow_ending=True)
    assert result.steps[-1].is_ending
    assert all(not s.is_blocking and not s.next_choices for s in result.steps)
    assert result.steps[-1].narration == "The notebook closes."


def test_buffered_tail_cannot_award_an_unearned_relationship_or_memory(validator, session):
    actual_response = beat(relationship_changes={"aiko": {"trust": 3}})
    tail = beat(
        narration="The notebook stays open.", relationship_changes={"aiko": {"trust": 5}},
        emotion={"aiko": "happy"}, flags_set={"promised_to_help": True},
        memory={"character": "aiko", "text": "Kai promised to finish every page."},
    )
    result = validator.validate(GeneratedRun(steps=[actual_response, question(), tail]), session)
    assert result.steps[0].relationship_changes["aiko"].trust == 3
    saved_tail = result.steps[-1]
    assert not saved_tail.relationship_changes and not saved_tail.flags_set
    assert not saved_tail.emotion and saved_tail.memory is None
    assert saved_tail.narration == tail.narration
    assert tail.memory is not None, "validation must not mutate the provider's payload"


@pytest.mark.parametrize("bad_tail", [
    {"type": "transition", "location": "rooftop", "narration": "The rooftop door opens."},
    {"location": "rooftop", "narration": "Everyone is now on the roof."},
    {"type": "event", "narration": "The exhibit is cancelled."},
    {"characters": ["aiko", "ren"], "narration": "Ren joins them."},
])
def test_branch_dependent_tail_is_discarded_not_relabelled(validator, session, bad_tail):
    result = validator.validate(GeneratedRun(steps=[
        beat(), question(), beat(**bad_tail), beat(narration="This depends on the invalid event."),
    ]), session)
    assert len(result.steps) == 2
    assert result.steps[-1].is_blocking


def test_an_inserted_decision_also_protects_the_tail(validator, session):
    steps = [beat(narration=f"A note numbered {i}.") for i in range(20)]
    steps[18].relationship_changes = {"aiko": RelationshipDelta(trust=5)}
    result = validator.validate(GeneratedRun(steps=steps), session)
    assert result.steps[14].is_blocking
    assert all(not s.relationship_changes for s in result.steps[15:])


def test_tail_visual_accepts_a_canonical_character_name(validator, session):
    report = validator.validate(GeneratedRun(steps=[question(), beat(
        visual={"background": "classroom", "character": "Aiko Serizawa"},
    )]), session)
    assert len(report.steps) == 2


def test_derived_summary_keeps_the_response_not_the_buffer():
    summary = NarrativeAgent._derive_summary([
        beat(narration="Aiko offers to share the work."), question(),
        beat(narration="A clock ticks."),
    ])
    assert summary == "Aiko offers to share the work."


@pytest.mark.parametrize("budget", [1, 3, 10, 14, 20])
def test_repair_never_exceeds_the_configured_step_budget(validator, session, budget):
    validator.max_steps = budget
    result = validator.validate(GeneratedRun(steps=[beat() for _ in range(budget)]), session)
    assert len(result.steps) <= budget
    assert sum(s.is_blocking for s in result.steps) == 1


def test_finale_prompts_do_not_demand_another_choice(world, session):
    system = build_system_prompt(world, max_steps=20, max_delta=5, rating="teen", finale=True)
    prompt = build_run_prompt(world, session, INTENT, [], history_steps=20,
                              decision=TYPED, directive=Directive(is_finale=True), max_steps=20)
    for text in (system, prompt):
        assert "exactly ONE decision" not in text
        assert "between step 10 and step 15" not in text
        assert "Do NOT emit choice or prompt" in text


def test_short_model_runs_get_a_possible_decision_position(world):
    text = build_system_prompt(world, max_steps=6, max_delta=5, rating="teen")
    assert "at the final step (step 6)" in text
    assert "between step 10 and step 15" not in text


def test_repaired_summary_cannot_remember_a_discarded_branch(world, validator, narrator, session):
    agent = NarrativeAgent(world, validator, narrator)
    result = agent._finish(GeneratedRun(summary="Kai and Aiko moved to the rooftop.", steps=[
        beat(), question(), beat(type="transition", location="rooftop", narration="On the rooftop."),
    ]), session, used_fallback=False, provider="test")
    assert "rooftop" not in result.summary
    assert result.steps[-1].is_blocking


def test_chapter_direction_changes_with_delivered_progress_not_queue_size(director, session):
    session.cursor = 4
    early = director.plan(session, INTENT, TYPED)
    session.steps = [story_step(i) for i in range(60)]
    queued = director.plan(session, INTENT, TYPED)
    assert early.chapter_progress == queued.chapter_progress
    session.cursor = 44
    late = director.plan(session, INTENT, TYPED)
    assert early.chapter_progress != late.chapter_progress
    assert early.chapter_question == late.chapter_question
    assert "not completed history" in late.render()


def test_private_threads_follow_trust_without_becoming_shared_knowledge(world, session):
    guarded = build_context(world, session, [], history_steps=20)
    assert world.character("aiko").secret in guarded
    assert "Keep this private" in guarded
    session.characters["aiko"].relationship.update(trust=60, familiarity=60)
    warm = build_context(world, session, [], history_steps=20)
    assert "partial, voluntary disclosure" in warm
    assert "Never give one character another's secret" in warm


@pytest.mark.parametrize("arc", ["prologue", "first_weeks", "festival", "summer", "resolution"])
@pytest.mark.parametrize("target", ["aiko", "ren", "mika", "haruto"])
def test_authored_chapters_stay_playable_without_branch_side_effects(
    world, director, narrator, validator, session, arc, target,
):
    session.world.arc = arc
    session.characters[target].relationship.update(trust=60, familiarity=60, affection=50)
    intent = PlayerIntent(action="help", target=target, raw="I offer to help.")
    run = narrator.run(session, intent, directive=director.plan(session, intent, TYPED))
    report = validator.validate(run, session)
    assert len(report.steps) == 20
    boundary = next(i for i, s in enumerate(report.steps) if s.is_blocking)
    assert 9 <= boundary <= 14
    assert sum(s.is_blocking for s in report.steps) == 1
    assert any(s.dialogue and s.dialogue.text in world.chapter(arc).lines[target]
               for s in report.steps[:boundary])
    assert all(s.type in (StepType.narration, StepType.dialogue) and not s.relationship_changes
               and not s.flags_set and not s.memory for s in report.steps[boundary + 1:])


@pytest.mark.parametrize("web_mode", [False, True])
async def test_provider_timeout_allows_failover_in_every_mode(world, validator, narrator, session, web_mode):
    class HangingChat:
        name = "hanging"
        async def complete_json(self, **kwargs):
            await asyncio.sleep(60)
    fallback = StubChat({"summary": "Aiko waits.", "steps": [llm_step(), llm_choice()]})
    agent = NarrativeAgent(world, validator, narrator, chat=HangingChat(), fallback_chats=[fallback],
                           web_mode=web_mode, attempt_timeout_s=0.01)
    result = await asyncio.wait_for(agent.generate(session, INTENT, []), timeout=1)
    assert result.ok and result.provider == fallback.name


async def test_retrieval_outage_does_not_replace_a_working_writer(world, tmp_path):
    chat = StubChat({"summary": "Aiko waits.", "steps": [llm_step(), llm_choice()]})
    engine = Engine(world, tmp_path, chat=chat)
    await engine.start(world)
    engine.memory.recall = AsyncMock(side_effect=ConnectionError("memory index down"))
    await engine.generation.submit("g1", INTENT, decision=TYPED)
    await engine.generation.drain()
    assert len(chat.calls) == 1
    assert not (await engine.games.get("g1")).pending.used_fallback


@pytest.mark.parametrize("hangs", [False, True])
async def test_memory_embedding_outage_keeps_text_and_relevance(hangs):
    class BrokenEmbedding:
        calls = 0
        async def embed(self, texts):
            self.calls += 1
            if hangs:
                await asyncio.sleep(60)
            raise ConnectionError("embedding service down")
    embedder = BrokenEmbedding()
    repository = InMemoryMemoryRepository()
    agent = MemoryAgent(embedder, repository, embedding_timeout_s=0.01)
    for index, text in enumerate(("Aiko missed the train.", "Aiko finished a blue postcard.")):
        await agent.remember("g1", MemoryProposal(character="aiko", text=text), step_index=index)
    recall = await agent.recall("g1", "blue postcard", characters=["aiko"], top_k=1)
    assert recall[0].text == "Aiko finished a blue postcard."
    assert embedder.calls == 1, "an outage must not cost a timeout per memory"
    assert all(not r.embedding for r in await repository.for_game("g1"))


async def test_memory_write_is_idempotent_and_scoped():
    repository = InMemoryMemoryRepository()
    agent = MemoryAgent(HashingEmbedding(), repository)
    proposal = MemoryProposal(character="aiko", text="Kai helped with a postcard.")
    first = await agent.remember("g1", proposal, step_index=2)
    replay = await agent.remember("g1", proposal, step_index=2)
    await agent.remember("g1", proposal, step_index=3)
    await agent.remember("g2", proposal, step_index=2)
    assert first.id == replay.id
    assert len(await repository.for_game("g1")) == 2
    assert len(await repository.for_game("g2")) == 1


async def test_memory_index_failure_does_not_withhold_a_story_beat(world, tmp_path):
    engine = Engine(world, tmp_path)
    session = await engine.start(world)
    session.steps = [story_step(0, relationship_changes={"aiko": {"trust": 3}},
                               memory={"character": "aiko", "text": "Kai helped with a postcard."})]
    await engine.games.save(session)
    engine.memory.remember = AsyncMock(side_effect=ConnectionError("memory index down"))
    delivered = await engine.service.next_step("g1")
    saved = await engine.games.get("g1")
    assert delivered.status == "ready" and saved.cursor == 0
    assert saved.characters["aiko"].value("trust") == session.characters["aiko"].value("trust") + 3
    assert saved.steps[0].memory.text == "Kai helped with a postcard."


@pytest.mark.parametrize("delivery", ["next_step", "next_batch", "skip_to_step"])
async def test_delivery_retry_does_not_duplicate_memory_or_relationships(world, tmp_path, monkeypatch, delivery):
    engine = Engine(world, tmp_path)
    session = await engine.start(world)
    session.steps = [story_step(0, relationship_changes={"aiko": {"trust": 3}},
                               memory={"character": "aiko", "text": "Kai helped with a postcard."})]
    await engine.games.save(session)
    save = engine.games.save
    async def fail_once(current):
        monkeypatch.setattr(engine.games, "save", save)
        raise StaleSessionError("a concurrent writer won")
    monkeypatch.setattr(engine.games, "save", fail_once)
    deliver = getattr(engine.service, delivery)
    kwargs = {"until_index": 0} if delivery == "skip_to_step" else {}
    with pytest.raises(StaleSessionError):
        await deliver("g1", **kwargs)
    assert not await engine.memories.for_game("g1"), "a failed delivery created a memory"
    await deliver("g1", **kwargs)
    saved = await engine.games.get("g1")
    assert saved.characters["aiko"].value("trust") == session.characters["aiko"].value("trust") + 3
    assert len(await engine.memories.for_game("g1")) == 1
