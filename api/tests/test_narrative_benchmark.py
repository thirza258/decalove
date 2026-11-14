"""Narrative benchmark — the intelligence PRD §5.37 scenarios, run offline.

These are the regression gates from §13.4 stated as executable expectations: a release
must not increase knowledge leakage, lose an unresolved memory, break delivery/commit
consistency, or let a secret spread to someone who was not there. Assertions are
structural and semantic, never exact prose.
"""

from __future__ import annotations

import pytest

from app.agents.context import ContextAssembler
from app.agents.knowledge import CharacterKnowledgeManager, secret_fact_id
from app.agents.memory_agent import MemoryAgent
from app.agents.narrative import NarrativeAgent
from app.agents.planner import NarrativePlanner
from app.agents.prompts import build_context, build_run_prompt
from app.agents.quality import NarrativeQualityEvaluator, QualityContext
from app.agents.safety import SafetyFilter
from app.agents.scripted import ScriptedNarrator
from app.agents.validator import Validator
from app.agents.visual import VisualAgent
from app.assets.local_store import LocalAssetStore
from app.domain.behavior import PlayerBehaviorProfile
from app.domain.direction import DecisionContext, DecisionKind, Directive
from app.domain.enums import Grounding, StepType
from app.domain.intent import PlayerIntent
from app.domain.memory import MemoryStatus
from app.domain.story import GeneratedRun, GeneratedStep, MemoryProposal, StoryStep
from app.llm.embeddings import HashingEmbedding
from app.llm.placeholder_image import PlaceholderImageProvider
from app.repositories.memory_repo import (
    InMemoryAssetRepository,
    InMemoryChronicleRepository,
    InMemoryGameRepository,
    InMemoryKnowledgeRepository,
    InMemoryMemoryRepository,
    InMemoryThreadRepository,
    InMemoryTraceRepository,
)
from app.services.asset_service import AssetService
from app.services.game_service import GameService
from app.services.generation import GenerationService
from app.services.tracing import TraceRecorder
from test_generation_service import INTENT, TYPED
from test_llm_path import StubChat, choice_step, step as llm_step


class Bench:
    """The whole engine, intelligence layer included, on in-memory stores."""

    def __init__(self, world, tmp_path, *, chat=None, quality=False):
        self.games = InMemoryGameRepository()
        self.memories = InMemoryMemoryRepository()
        self.chronicle = InMemoryChronicleRepository()
        self.knowledge_repo = InMemoryKnowledgeRepository()
        self.thread_repo = InMemoryThreadRepository()
        self.traces = InMemoryTraceRepository()
        self.assets_repo = InMemoryAssetRepository()

        validator = Validator(world=world, safety=SafetyFilter(), max_delta=5, max_steps=10)
        scripted = ScriptedNarrator(world)
        self.narrative = NarrativeAgent(
            world, validator, scripted, chat=chat, max_steps=10,
            quality=NarrativeQualityEvaluator() if quality else None,
        )
        self.memory = MemoryAgent(HashingEmbedding(), self.memories)
        self.knowledge = CharacterKnowledgeManager(self.knowledge_repo, world=world)
        self.planner = NarrativePlanner(self.thread_repo, world=world)
        self.tracer = TraceRecorder(self.traces)
        self.context = ContextAssembler(
            memory=self.memory, knowledge=self.knowledge, planner=self.planner,
            chronicle=self.chronicle,
        )
        self.visual = VisualAgent(world)
        self.assets = AssetService(
            self.assets_repo, LocalAssetStore(tmp_path), PlaceholderImageProvider(),
            enabled=False,
        )
        self.generation = GenerationService(
            games=self.games, narrative=self.narrative, director=_director(world),
            memory=self.memory, chronicle=self.chronicle, visual=self.visual,
            assets=self.assets, timeout_s=5.0, context=self.context,
            planner=self.planner, tracer=self.tracer,
        )
        self.service = GameService(
            world=world, games=self.games, director=_director(world),
            narrative=self.narrative, memory=self.memory, chronicle=self.chronicle,
            visual=self.visual, assets=self.assets, generation=self.generation,
            knowledge=self.knowledge, planner=self.planner, tracer=self.tracer,
        )

    async def start(self, world):
        from app.domain.state import CharacterState, GameSession, PlayerProfile, WorldState

        session = GameSession(
            id="g1", world_id=world.id, player=PlayerProfile(name="Kai"),
            world=WorldState(location="classroom", present_characters=["aiko", "ren"]),
            characters={
                character.id: CharacterState(
                    id=character.id, name=character.name,
                    relationship=dict(character.starting_relationship),
                )
                for character in world.characters
            },
        )
        await self.games.create(session)
        await self.knowledge.seed(session.id, session)
        return session


def _director(world):
    from app.agents.director import DirectorAgent

    return DirectorAgent(world)


@pytest.fixture
async def bench(world, tmp_path):
    built = Bench(world, tmp_path)
    await built.start(world)
    yield built
    await built.generation.shutdown()


# -- scenario 1: a broken promise is remembered and still matters ----------------------

async def test_broken_promise_is_retrievable_many_chapters_later(bench, world, session):
    await bench.memory.remember(
        "g1",
        MemoryProposal(
            character="aiko", text="Kai promised to finish the mural and never did.",
            importance=0.9, event_type="promise", status="unresolved",
        ),
        step_index=2, source_step_id="step_00002",
    )
    for index in range(3, 60):
        await bench.memory.remember(
            "g1", MemoryProposal(character="aiko", text=f"Ordinary lunch number {index}."),
            step_index=index,
        )
    remembered = await bench.memory.recall("g1", "the finished mural", characters=["aiko"])
    assert any("mural" in record.text for record in remembered)

    prompt = build_run_prompt(
        world, session, INTENT, remembered, history_steps=20,
        decision=DecisionContext(kind=DecisionKind.free_text, typed="I ask about the mural"),
        directive=Directive(), max_steps=10,
    )
    assert "promised to finish the mural" in prompt


# -- scenario 2: an old conflict is recalled -----------------------------------------

async def test_an_old_conflict_stays_in_the_narrative_s_context(bench, world, session):
    session.characters["aiko"].met = True
    session.characters["aiko"].relationship["anger"] = 45
    session.cursor = 180
    await bench.planner.sync(session, [])
    prompt = build_context(
        world, session, [], history_steps=5,
        threads=await bench.planner.get_active_threads(session.id),
    )
    assert "Unresolved friction with Aiko" in prompt


# -- scenarios 3 and 7: secrets and absence ------------------------------------------

async def test_a_secret_reaches_only_the_people_who_were_there(bench, world, session):
    secret = world.character("aiko").secret
    step = StoryStep(
        step_id="step_00005", index=5, batch_id="b1", type=StepType.dialogue,
        location="classroom", characters=["aiko", "ren"],
        dialogue={"speaker": "aiko", "text": secret},
    )
    await bench.knowledge.acquire_from_step(session, step)
    knowledge = await bench.knowledge.for_game(session.id)
    fact = secret_fact_id(session.id, "aiko")

    assert any(record.fact_id == fact for record in knowledge["ren"])
    assert "mika" not in knowledge
    assert "haruto" not in knowledge
    rendered = bench.knowledge.render(knowledge, ["aiko", "ren", "mika"])
    assert "Mika" in rendered and "no established knowledge" in rendered


# -- scenario 4: rejection carries forward -------------------------------------------

async def test_a_rejection_is_not_forgotten_by_the_next_scene(bench, world, session):
    await bench.memory.remember(
        "g1",
        MemoryProposal(
            character="aiko", text="Aiko turned Kai down and asked for space.",
            importance=0.9, event_type="rejection", category="relationship",
        ),
        step_index=4,
    )
    recalled = await bench.memory.recall("g1", "asking her again", characters=["aiko"])
    assert any("turned Kai down" in record.text for record in recalled)


# -- scenario 5: an apology does not guarantee forgiveness ---------------------------

async def test_an_apology_does_not_rewrite_the_relationship_by_itself(world, tmp_path):
    chat = StubChat({"summary": "Aiko listens.", "steps": [llm_step(), choice_step()]})
    bench = Bench(world, tmp_path, chat=chat)
    await bench.start(world)
    before = (await bench.games.get("g1")).characters["aiko"].value("trust")

    await bench.generation.submit(
        "g1",
        PlayerIntent(action="apologise", target="aiko", risk="medium", raw="I'm sorry"),
        decision=TYPED,
    )
    await bench.generation.drain()
    # Generation alone changes nothing: an unread apology is not yet a story event.
    assert (await bench.games.get("g1")).characters["aiko"].value("trust") == before

    await bench.service.next_batch("g1", limit=20)
    after = (await bench.games.get("g1")).characters["aiko"].value("trust")
    # The stub's beat proposes a +2 affection and no trust; forgiveness is not free.
    assert after == before
    await bench.generation.shutdown()


# -- scenario 6: compound intent -----------------------------------------------------

def test_a_compound_input_carries_both_intentions(world, director, session):
    intent = director.parse_keywords(session, "I apologise to Aiko, but I defend Ren.")
    assert {component.target for component in intent.components} >= {"aiko", "ren"}
    prompt = build_run_prompt(
        world, session, intent, [], history_steps=5,
        decision=DecisionContext(kind=DecisionKind.free_text, typed=intent.raw),
        directive=Directive(), max_steps=20,
    )
    assert "Also attempting" in prompt


# -- scenario 8: contradictory beliefs ----------------------------------------------

async def test_two_characters_can_believe_different_things_about_one_event(bench, session):
    from app.domain.knowledge import CharacterKnowledge, KnowledgeType

    base = dict(
        game_id=session.id, fact_id="event:argument",
        proposition="Kai started the argument.",
        knowledge_type=KnowledgeType.believed, acquisition_method="witnessed",
    )
    await bench.knowledge_repo.upsert(CharacterKnowledge(
        id="ka", character_id="aiko", **base,
    ))
    await bench.knowledge_repo.upsert(CharacterKnowledge(
        id="kr", game_id=session.id, character_id="ren", fact_id="event:argument",
        proposition="Ren thinks Aiko started it.",
        knowledge_type=KnowledgeType.misconception, acquisition_method="inferred",
    ))
    knowledge = await bench.knowledge.for_game(session.id)
    assert knowledge["aiko"][0].proposition != knowledge["ren"][0].proposition
    assert knowledge["ren"][0].knowledge_type is KnowledgeType.misconception


# -- scenario 9: repeated conversation is detected ----------------------------------

def test_previously_delivered_information_is_scored_as_repetition(session):
    delivered = "Aiko holds the blue notebook open."
    report = NarrativeQualityEvaluator().evaluate(
        [
            GeneratedStep(type="narration", location="classroom", characters=["aiko"],
                          narration=delivered),
            GeneratedStep(type="choice", location="classroom", characters=["aiko"],
                          narration="Aiko waits.", next_choices=[
                              {"id": "a", "text": "Offer to help."},
                              {"id": "b", "text": "Ask why."},
                              {"id": "c", "text": "Leave."},
                          ]),
        ],
        QualityContext(
            session=session, intent=PlayerIntent(action="help", target="aiko"),
            directive=Directive(), recent_beats=[delivered],
        ),
    )
    assert report.scores["repetition"] < 0.5


# -- scenario 10: an impossible action does not change the world --------------------

def test_an_impossible_attempt_is_heard_but_never_enacted(world, validator, session):
    from app.agents.grounding import classify

    assert classify("I summon a dragon to impress Aiko") is Grounding.off_world
    run = GeneratedRun(steps=[
        # A narration step cannot move the scene: only a transition may.
        GeneratedStep(type="narration", location="rooftop", characters=["aiko"],
                      narration="The rooftop is empty."),
        GeneratedStep(type="choice", location="rooftop", characters=["aiko"],
                      narration="Aiko waits.", next_choices=[
                          {"id": "a", "text": "Offer to help."},
                          {"id": "b", "text": "Ask why."},
                          {"id": "c", "text": "Leave."},
                      ]),
    ])
    report = validator.validate(run, session)
    # A move without a transition is not allowed; the first step is snapped back.
    assert report.steps[0].location == "classroom"
    assert session.world.location == "classroom"


# -- scenario 11: resolved threads stop being active --------------------------------

async def test_a_resolved_thread_stops_influencing_the_prompt(bench, world, session):
    await bench.memory.remember(
        session.id,
        MemoryProposal(
            character="aiko", text="Kai promised the notebook.",
            event_type="promise", status="unresolved", importance=0.8,
        ),
        step_index=0,
    )
    await bench.planner.sync(session, await bench.memories.for_game(session.id))
    active = await bench.planner.get_active_threads(session.id)
    assert any(thread.thread_type.value == "promise" for thread in active)

    await bench.memory.remember(
        session.id,
        MemoryProposal(
            character="aiko", text="Kai delivered the finished notebook.",
            event_type="promise", status="fulfilled", importance=0.8,
        ),
        step_index=6,
    )
    await bench.planner.sync(session, await bench.memories.for_game(session.id))
    active = await bench.planner.get_active_threads(session.id)
    assert all(thread.thread_type.value != "promise" for thread in active)


# -- scenario 12: character voice ---------------------------------------------------

def test_distinct_speakers_score_better_than_one_voice_for_the_cast(session):
    evaluator = NarrativeQualityEvaluator()

    def run(dialogue_steps):
        return evaluator.evaluate(
            dialogue_steps + [GeneratedStep(
                type="choice", location="classroom", characters=["aiko"],
                narration="Aiko waits.", next_choices=[
                    {"id": "a", "text": "Offer to help."},
                    {"id": "b", "text": "Ask why."},
                    {"id": "c", "text": "Leave."},
                ],
            )],
            QualityContext(
                session=session, intent=PlayerIntent(action="help", target="aiko"),
                directive=Directive(),
            ),
        )

    one_voice = run([
        GeneratedStep(type="dialogue", location="classroom", characters=["aiko", "ren"],
                      dialogue={"speaker": "aiko", "text": "I have been waiting."}),
    ])
    two_voices = run([
        GeneratedStep(type="dialogue", location="classroom", characters=["aiko", "ren"],
                      dialogue={"speaker": "aiko", "text": "I have been waiting."}),
        GeneratedStep(type="dialogue", location="classroom", characters=["aiko", "ren"],
                      dialogue={"speaker": "ren", "text": "Then maybe you should have "
                                "said something sooner instead of letting it sit there "
                                "all afternoon, honestly."}),
    ])
    assert two_voices.scores["character_voice"] > one_voice.scores["character_voice"]


# -- Phase 1: traces and delivery consistency ---------------------------------------

async def test_every_generated_run_is_traceable_to_its_prompt_version_and_context(
    world, tmp_path
):
    chat = StubChat({"summary": "Aiko listens.", "steps": [llm_step(), choice_step()]})
    bench = Bench(world, tmp_path, chat=chat)
    await bench.start(world)
    await bench.memory.remember(
        "g1", MemoryProposal(character="aiko", text="Kai borrowed her eraser."), step_index=0,
    )
    await bench.generation.submit("g1", INTENT, decision=TYPED)
    await bench.generation.drain()

    traces = await bench.traces.for_game("g1")
    assert len(traces) == 1
    trace = traces[0]
    assert trace.prompt_version and trace.provider == "stub"
    assert trace.committed is True and trace.delivered is False
    assert trace.intent["action"] == "talk_to"
    assert trace.memory_ids, "the trace did not record what context the model was given"
    assert trace.output_steps and trace.prompt_chars and trace.latency_ms > 0

    await bench.service.next_batch("g1", limit=20)
    trace = (await bench.traces.for_game("g1"))[0]
    assert trace.delivered is True
    await bench.generation.shutdown()


async def test_a_delivered_batch_cannot_index_knowledge_twice(bench):
    chat_driven = StubChat({"summary": "Aiko waits.", "steps": [llm_step(), choice_step()]})
    bench.generation.narrative.chat = chat_driven
    await bench.generation.submit("g1", INTENT, decision=TYPED)
    await bench.generation.drain()
    delivered = await bench.service.next_batch("g1", limit=20)
    session = await bench.games.get("g1")
    first = await bench.knowledge.for_game("g1")

    # Replaying the same delivery (a lost response, a retried request) changes nothing:
    # acquisition is keyed by (game, character, fact) and upserts.
    await bench.service._absorb_delivery(session, delivered.steps)
    second = await bench.knowledge.for_game("g1")
    assert {c: len(f) for c, f in first.items()} == {c: len(f) for c, f in second.items()}
    await bench.generation.shutdown()
