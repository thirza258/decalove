"""Narrative threads, behaviour modelling and choice diversity — FR-05, FR-06, FR-07."""

from __future__ import annotations

from app.agents.behavior import observe_delivery
from app.agents.choices import assess, classify, repair
from app.agents.planner import NarrativePlanner
from app.domain.behavior import PlayerBehaviorProfile
from app.domain.intent import PlayerIntent
from app.domain.memory import CharacterMemory, MemoryStatus
from app.domain.story import Choice, GeneratedStep
from app.repositories.memory_repo import InMemoryThreadRepository


def memory(character="aiko", text="Kai promised the notebook by Friday.", **kwargs):
    return CharacterMemory(
        id=kwargs.pop("id", f"m-{text[:8]}"),
        game_id="test-game",
        character=character,
        text=text,
        event_type=kwargs.pop("event_type", "promise"),
        subject=kwargs.pop("subject", character),
        status=kwargs.pop("status", MemoryStatus.unresolved),
        importance=kwargs.pop("importance", 0.8),
        step_index=kwargs.pop("step_index", 0),
        **kwargs,
    )


def planner(world, **kwargs):
    return NarrativePlanner(InMemoryThreadRepository(), world=world, **kwargs)


class TestThreadLifecycle:
    async def test_an_unresolved_promise_becomes_an_active_thread(self, world, session):
        engine = planner(world)
        threads = await engine.sync(session, [memory()])
        promise = next(t for t in threads if t.thread_type.value == "promise")
        assert promise.open
        assert promise.involved_characters == ["aiko"]
        assert "Aiko" in promise.title

    async def test_a_fulfilled_promise_is_no_longer_an_active_conflict(self, world, session):
        engine = planner(world)
        await engine.sync(session, [memory()])
        threads = await engine.sync(session, [memory(
            id="m2", text="Kai kept the notebook promise.", status=MemoryStatus.fulfilled,
            step_index=4,
        )])
        promise = next(t for t in threads if t.thread_type.value == "promise")
        assert promise.status.value == "resolved"
        assert not promise.open
        assert all(t.thread_type.value != "conflict" for t in threads)

    async def test_an_old_thread_goes_dormant_but_stays_available(self, world, session):
        engine = planner(world, dormant_after_steps=5)
        session.cursor = 30
        threads = await engine.sync(session, [memory(step_index=0)])
        promise = next(t for t in threads if t.thread_type.value == "promise")
        assert promise.status.value == "dormant"
        assert promise.open, "a dormant thread is still retrievable"
        rendered = engine.render(await engine.get_active_threads(session.id))
        assert "dormant" in rendered and "Aiko" in rendered

    async def test_unresolved_friction_is_derived_from_live_state(self, world, session):
        engine = planner(world)
        session.characters["aiko"].met = True
        session.characters["aiko"].relationship["anger"] = 40
        threads = await engine.sync(session, [])
        conflict = next(t for t in threads if t.thread_type.value == "conflict")
        assert conflict.open and conflict.priority > 0.5

        session.characters["aiko"].relationship["anger"] = 0
        session.characters["aiko"].relationship["trust"] = 60
        await engine.sync(session, [])
        stored = await engine.repository.for_game(session.id)
        assert all(
            thread.status.value == "resolved"
            for thread in stored if thread.thread_type.value == "conflict"
        ), "a settled conflict must stop being treated as active"

    async def test_a_met_character_with_a_secret_opens_a_mystery_when_trust_allows(
        self, world, session
    ):
        engine = planner(world)
        session.characters["aiko"].met = True
        session.characters["aiko"].relationship.update(trust=10, familiarity=10)
        threads = await engine.sync(session, [])
        mystery = next(t for t in threads if t.thread_type.value == "mystery")
        assert mystery.status.value == "dormant"

        session.characters["aiko"].relationship.update(trust=60, familiarity=60)
        threads = await engine.sync(session, [])
        mystery = next(t for t in threads if t.thread_type.value == "mystery")
        assert mystery.status.value == "active"

    async def test_the_planner_suggests_but_never_dictates(self, world, session):
        engine = planner(world)
        threads = await engine.sync(session, [memory()])
        note = engine.suggestions(threads, session)
        assert "promise" in note.lower()
        assert "do not" in note.lower()

    async def test_sync_is_idempotent(self, world, session):
        engine = planner(world)
        first = await engine.sync(session, [memory()])
        second = await engine.sync(session, [memory()])
        assert [thread.id for thread in first] == [thread.id for thread in second]
        assert len(await engine.repository.for_game(session.id)) == len(first)


class TestBehaviorProfile:
    def test_a_single_action_does_not_define_the_player(self):
        profile = PlayerBehaviorProfile()
        profile.observe("risk_tolerance", 1.0, step_id="b1")
        assert 0.5 < profile.value("risk_tolerance") < 0.75
        assert profile.confidence("risk_tolerance") < 0.25

    def test_confidence_grows_with_evidence(self):
        profile = PlayerBehaviorProfile()
        for index in range(6):
            profile.observe("empathy", 1.0, step_id=f"b{index}")
        assert profile.value("empathy") > 0.8
        assert profile.confidence("empathy") > 0.5

    def test_a_redelivered_batch_does_not_double_count(self):
        profile = PlayerBehaviorProfile()
        profile.observe("empathy", 1.0, step_id="b1")
        before = profile.value("empathy")
        profile.observe("empathy", 0.0, step_id="b1")
        assert profile.value("empathy") == before
        assert profile.evidence_count["empathy"] == 1

    def test_contradictory_evidence_is_kept_not_averaged_away(self):
        profile = PlayerBehaviorProfile()
        for index in range(5):
            profile.observe("empathy", 1.0, step_id=f"kind{index}")
        profile.observe("empathy", 0.0, step_id="cruel")
        assert profile.conflicting_evidence["empathy"] == 1
        assert profile.value("empathy") > 0.5, "one contradiction must not erase a pattern"

    def test_the_note_stays_quiet_until_there_is_a_pattern(self):
        profile = PlayerBehaviorProfile()
        assert profile.note() == ""
        for index in range(5):
            profile.observe("empathy", 1.0, step_id=f"b{index}")
        assert "looking out for other people" in profile.note()

    def test_the_same_pattern_reads_differently_through_each_character(self):
        profile = PlayerBehaviorProfile()
        for index in range(5):
            profile.observe("empathy", 1.0, step_id=f"b{index}")
        guarded = profile.note_for("aiko", warmth=10)
        warm = profile.note_for("ren", warmth=80)
        assert "uncharitably" in guarded
        assert "benefit of the doubt" in warm

    def test_delivery_records_evidence_without_forcing_outcomes(self, session):
        profile = PlayerBehaviorProfile()
        intent = PlayerIntent(action="help", target="aiko", emotion="warm", risk="low")
        observe_delivery(profile, intent, [], batch_id="batch-1", step_index=3)
        assert profile.evidence_count
        assert profile.value("empathy") > 0.5
        assert profile.updated_at_step == 3

    def test_a_broken_promise_is_evidence_about_commitment(self, session):
        profile = PlayerBehaviorProfile()
        step = GeneratedStep(
            type="narration", location="classroom", characters=["aiko"],
            narration="The notebook stays unfinished.",
            memory={
                "character": "aiko", "text": "Kai never finished it.",
                "event_type": "promise", "status": "broken",
            },
        )
        observe_delivery(
            profile, PlayerIntent(action="observe", risk="low"), [step],
            batch_id="batch-2",
        )
        assert profile.value("commitment") < 0.5


class TestChoiceDiversity:
    def test_paraphrases_are_classified_as_one_intention(self):
        assert classify("Say nothing.") == classify("Stay silent.")
        assert classify("Offer to help.") != classify("Ask why she is upset.")

    def test_a_distinct_menu_scores_higher_than_paraphrases(self):
        distinct = assess([
            Choice(id="a", text="Offer to help with the page."),
            Choice(id="b", text="Ask why she is upset."),
            Choice(id="c", text="Tell her you cannot stay."),
        ])
        samey = assess([
            Choice(id="a", text="Say nothing."),
            Choice(id="b", text="Say nothing at all."),
            Choice(id="c", text="Stay silent."),
        ])
        assert distinct.score > samey.score
        assert samey.duplicate_pairs

    def test_repair_removes_paraphrases_and_tops_up_from_the_bank(self):
        repaired = repair(
            [
                Choice(id="a", text="Say nothing."),
                Choice(id="b", text="Say nothing at all."),
            ],
            bank=("Ask what she meant.", "Offer to help."),
            min_choices=3,
        )
        assert len(repaired) == 3
        assert len({choice.text for choice in repaired}) == 3
        assert [choice.id for choice in repaired] == ["choice_1", "choice_2", "choice_3"]

    def test_repair_leaves_a_good_menu_untouched(self):
        choices = [
            Choice(id="a", text="Offer to help with the page."),
            Choice(id="b", text="Ask why she is upset."),
            Choice(id="c", text="Tell her you cannot stay."),
        ]
        assert repair(choices, bank=(), min_choices=3) is choices
