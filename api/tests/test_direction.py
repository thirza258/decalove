"""The Director's planning stage — PRD §9.1, and §15's branching-by-state.

The point of this layer is that the engine, not the model, decides the shape of a
scene: pacing, who carries it, how each character is disposed, and whether the
player's attempt is allowed to fail. All of it derived from state, deterministically.
"""

from __future__ import annotations

import pytest

from app.agents.director import DirectorAgent
from app.domain.direction import DecisionContext, DecisionKind, Directive, Pacing, PlayerStyle
from app.domain.enums import Risk, StepType
from app.domain.intent import PlayerIntent
from app.domain.story import GeneratedStep, StoryStep

TYPED = DecisionContext(kind=DecisionKind.free_text, typed="I say something to Aiko")


def relationship(session, character="aiko", **values):
    session.characters[character].relationship.update(values)
    return session


def append(session, index, step_type=StepType.narration, location="classroom"):
    session.steps.append(
        StoryStep(
            **GeneratedStep(type=step_type, location=location, narration=".").model_dump(),
            step_id=f"step_{index:05d}",
            index=index,
            batch_id="b",
        )
    )


@pytest.fixture
def director(world):
    return DirectorAgent(world)


class TestStance:
    """PRD §15: the same action means different things at different relationships."""

    def test_a_stranger_is_uninvested(self, director, session):
        relationship(session, familiarity=5, trust=10)
        stance = director.plan(session, PlayerIntent(action="talk_to", target="aiko"), TYPED).stance_for("aiko")

        assert "stranger" in stance.posture
        assert stance.conflict_mode == "cold"
        assert stance.receptive is False

    def test_anger_outranks_affection(self, director, session):
        relationship(session, affection=80, trust=70, familiarity=60, anger=40)
        stance = director.plan(session, PlayerIntent(action="talk_to", target="aiko"), TYPED).stance_for("aiko")

        assert "carrying something" in stance.posture
        assert stance.receptive is False, "warmth has to get past the anger first"

    def test_low_trust_deflects(self, director, session):
        relationship(session, affection=60, trust=15, familiarity=40)
        stance = director.plan(session, PlayerIntent(action="ask_about", target="aiko"), TYPED).stance_for("aiko")

        assert stance.posture == "guarded"
        assert stance.conflict_mode == "serious"

    def test_romance_makes_nothing_casual(self, director, session):
        relationship(session, affection=60, trust=60, romance=70, familiarity=50)
        stance = director.plan(session, PlayerIntent(action="talk_to", target="aiko"), TYPED).stance_for("aiko")

        assert "reading more into gestures" in stance.posture
        assert "romance 70" in stance.note

    def test_the_prd_example_playful_versus_serious_conflict(self, director, session):
        """'Player insults Aiko': affection 60 is a playful argument, 20 is a real one."""
        insult = PlayerIntent(action="tease", target="aiko", risk=Risk.high)

        relationship(session, affection=60, trust=50, familiarity=40)
        assert director.plan(session, insult, TYPED).stance_for("aiko").conflict_mode == "playful"

        relationship(session, affection=20, trust=15, familiarity=40)
        assert director.plan(session, insult, TYPED).stance_for("aiko").conflict_mode == "serious"

    def test_stance_notes_quote_the_actual_numbers(self, director, session):
        relationship(session, affection=52, trust=47, familiarity=40)
        stance = director.plan(session, PlayerIntent(action="talk_to", target="aiko"), TYPED).stance_for("aiko")
        assert "affection 52" in stance.note and "trust 47" in stance.note


class TestTension:
    def test_risk_sets_the_floor(self, director, session):
        relationship(session, trust=0)
        low = director.plan(session, PlayerIntent(action="observe", risk=Risk.low, target="aiko"), TYPED)
        high = director.plan(session, PlayerIntent(action="confess", risk=Risk.high, target="aiko"), TYPED)
        assert high.tension > low.tension

    def test_trust_lowers_it_and_anger_raises_it(self, director, session):
        base = PlayerIntent(action="ask_about", risk=Risk.medium, target="aiko")

        relationship(session, trust=90, anger=0, jealousy=0)
        calm = director.plan(session, base, TYPED).tension

        relationship(session, trust=5, anger=60, jealousy=40)
        fraught = director.plan(session, base, TYPED).tension

        assert fraught > calm

    def test_typing_a_risky_move_yourself_counts_for_more(self, director, session):
        intent = PlayerIntent(action="confess", risk=Risk.high, target="aiko")
        chosen = DecisionContext(kind=DecisionKind.choice, chosen_text="I love you")

        typed = director.plan(session, intent, TYPED).tension
        picked = director.plan(session, intent, chosen).tension
        assert typed > picked

    def test_an_unprompted_continuation_lowers_it(self, director, session):
        intent = PlayerIntent(action="observe", risk=Risk.low, target="aiko")
        auto = director.plan(session, intent, DecisionContext(kind=DecisionKind.auto))
        assert auto.tension < director.plan(session, intent, TYPED).tension

    def test_it_stays_inside_zero_and_one_hundred(self, director, session):
        for character in session.characters.values():
            character.relationship.update({"anger": 100, "jealousy": 100, "trust": 0})
        assert 0 <= director.plan(session, PlayerIntent(action="confess", risk=Risk.high), TYPED).tension <= 100

        for character in session.characters.values():
            character.relationship.update({"anger": 0, "jealousy": 0, "trust": 100})
        assert 0 <= director.plan(session, PlayerIntent(action="observe", risk=Risk.low), TYPED).tension <= 100


class TestPacing:
    def test_high_tension_is_charged(self, director, session):
        relationship(session, trust=0, anger=30)
        plan = director.plan(session, PlayerIntent(action="confess", risk=Risk.high, target="aiko"), TYPED)
        assert plan.pacing is Pacing.charged

    def test_a_charged_run_is_always_followed_by_release(self, director, session):
        """Two peaks back to back means neither one lands."""
        session.last_directive = Directive(pacing=Pacing.charged, tension=90)
        plan = director.plan(session, PlayerIntent(action="talk_to", risk=Risk.medium, target="aiko"), TYPED)

        assert plan.pacing is Pacing.release
        assert "come down" in plan.beat_goal

    def test_a_calm_moment_is_quiet(self, director, session):
        relationship(session, trust=90)
        plan = director.plan(session, PlayerIntent(action="observe", risk=Risk.low, target="aiko"), TYPED)
        assert plan.pacing is Pacing.quiet
        assert "stay small" in plan.beat_goal

    def test_a_long_stretch_with_nothing_happening_starts_building(self, director, session):
        relationship(session, trust=95)
        for index in range(20):
            append(session, index)
        plan = director.plan(session, PlayerIntent(action="observe", risk=Risk.low, target="aiko"), TYPED)
        assert plan.pacing is Pacing.building


class TestLocationPressure:
    def test_a_scene_that_has_stood_still_gets_moved(self, director, session):
        for index in range(20):
            append(session, index)
        plan = director.plan(session, PlayerIntent(action="talk_to", target="aiko"), TYPED)

        assert plan.push_location is not None
        assert plan.push_location != session.world.location

    def test_a_recent_transition_leaves_the_scene_alone(self, director, session):
        for index in range(20):
            append(session, index, step_type=StepType.transition if index == 18 else StepType.narration)
        assert director.plan(session, PlayerIntent(action="talk_to", target="aiko"), TYPED).push_location is None

    def test_the_peak_of_a_scene_is_never_interrupted(self, director, session):
        relationship(session, trust=0, anger=40)
        for index in range(30):
            append(session, index)
        plan = director.plan(session, PlayerIntent(action="confess", risk=Risk.high, target="aiko"), TYPED)

        assert plan.pacing is Pacing.charged
        assert plan.push_location is None

    def test_the_suggested_location_suits_the_time_of_day(self, director, session, world):
        session.world.time_of_day = "night"
        for index in range(20):
            append(session, index)
        plan = director.plan(session, PlayerIntent(action="talk_to", target="aiko"), TYPED)

        location = world.location(plan.push_location)
        assert "night" in location.times, f"{location.id} is not a night-time location"

    def test_it_is_deterministic(self, director, session):
        for index in range(20):
            append(session, index)
        intent = PlayerIntent(action="talk_to", target="aiko")
        assert (
            director.plan(session, intent, TYPED).push_location
            == director.plan(session, intent, TYPED).push_location
        )


class TestFocus:
    def test_the_addressed_character_leads(self, director, session):
        plan = director.plan(session, PlayerIntent(action="talk_to", target="haruto"), TYPED)
        assert plan.focus[0] == "haruto"

    def test_whoever_is_present_fills_in_behind_them(self, director, session):
        plan = director.plan(session, PlayerIntent(action="observe"), TYPED)
        assert plan.focus == ["aiko", "ren"]

    def test_it_is_capped_so_no_run_juggles_the_whole_cast(self, director, session):
        session.world.present_characters = ["aiko", "ren", "mika", "haruto"]
        assert len(director.plan(session, PlayerIntent(action="observe"), TYPED).focus) <= 3

    def test_an_empty_room_falls_back_to_whoever_is_best_known(self, director, session):
        session.world.present_characters = []
        relationship(session, "haruto", familiarity=90)
        assert director.plan(session, PlayerIntent(action="observe"), TYPED).focus == ["haruto"]


class TestBeatGoal:
    @pytest.mark.parametrize(
        ("kind", "fragment"),
        [
            (DecisionKind.opening, "introduce the place"),
            (DecisionKind.auto, "hand control straight back"),
        ],
    )
    def test_the_goal_follows_the_decision_kind(self, director, session, kind, fragment):
        plan = director.plan(session, PlayerIntent(action="observe", risk=Risk.low), DecisionContext(kind=kind))
        assert fragment in plan.beat_goal

    def test_an_exposed_player_is_flagged_to_the_writer(self, director, session):
        plan = director.plan(session, PlayerIntent(action="confess", risk=Risk.high, target="aiko"), TYPED)
        assert "They are exposed here" in plan.beat_goal
        assert plan.allow_failure is True

    def test_a_guarded_character_makes_failure_allowed(self, director, session):
        relationship(session, trust=10, familiarity=40)
        plan = director.plan(session, PlayerIntent(action="ask_about", risk=Risk.low, target="aiko"), TYPED)
        assert plan.allow_failure is True

    def test_a_warm_low_risk_move_is_expected_to_land(self, director, session):
        relationship(session, affection=70, trust=70, familiarity=60)
        plan = director.plan(session, PlayerIntent(action="talk_to", risk=Risk.low, target="aiko"), TYPED)
        assert plan.allow_failure is False

    def test_the_arc_shapes_the_note(self, director, session):
        session.world.arc = "festival"
        assert "deadline" in director.plan(session, PlayerIntent(action="talk_to"), TYPED).arc_note

        session.world.arc = "unknown_arc"
        assert director.plan(session, PlayerIntent(action="talk_to"), TYPED).arc_note == ""


class TestPlayerStyle:
    def test_it_says_nothing_until_it_has_seen_enough(self):
        style = PlayerStyle()
        assert "Too early" in style.note()
        style.record(kind=DecisionKind.choice, risk="low", target="aiko")
        assert "Too early" in style.note()

    def test_it_notices_a_player_who_writes_rather_than_picks(self):
        style = PlayerStyle()
        for _ in range(5):
            style.record(kind=DecisionKind.free_text, risk="high", target="aiko")
        note = style.note()

        assert "writes their own moves" in note
        assert "risky, direct" in note
        assert "returning to aiko" in note

    def test_it_notices_a_cautious_menu_player(self):
        style = PlayerStyle()
        for _ in range(8):
            style.record(kind=DecisionKind.choice, risk="low", target=None)
        note = style.note()

        assert "sticks to the options offered" in note
        assert "hangs back" in note

    def test_the_favourite_needs_real_weight_behind_it(self):
        style = PlayerStyle()
        for character in ("aiko", "ren", "mika", "haruto"):
            style.record(kind=DecisionKind.choice, risk="medium", target=character)
        assert "returning to" not in style.note(), "one turn each is not a favourite"

    def test_an_even_player_gets_an_even_note(self):
        style = PlayerStyle()
        for index in range(6):
            style.record(
                kind=DecisionKind.free_text if index % 2 else DecisionKind.choice,
                risk="medium",
                target=None,
            )
        assert style.note() == "This player plays evenly."


class TestStateChangesTheStoryOffline:
    """The whole point, visible without an API key."""

    def test_the_same_action_plays_differently_at_different_trust(self, world, narrator, director, session):
        intent = PlayerIntent(action="invite_character", target="aiko", risk=Risk.medium, raw="walk home?")

        relationship(session, affection=70, trust=70, familiarity=60)
        warm_plan = director.plan(session, intent, TYPED)
        warm = narrator.run(session, intent, directive=warm_plan)

        relationship(session, affection=10, trust=5, familiarity=8)
        cold_plan = director.plan(session, intent, TYPED)
        cold = narrator.run(session, intent, directive=cold_plan)

        assert warm_plan.allow_failure is False
        assert cold_plan.allow_failure is True

        warm_lines = [s.dialogue.text for s in warm.steps if s.dialogue]
        cold_lines = [s.dialogue.text for s in cold.steps if s.dialogue]
        assert warm_lines != cold_lines, "relationship state made no difference to the prose"
        assert "turned it down" in cold.summary
        assert "took it well enough" in warm.summary

    def test_a_rebuff_still_leaves_a_memory(self, narrator, director, session):
        """Being turned down is at least as memorable as being accepted."""
        intent = PlayerIntent(action="confess", target="aiko", risk=Risk.high, raw="I love you")
        relationship(session, affection=10, trust=5, familiarity=8)

        run = narrator.run(session, intent, directive=director.plan(session, intent, TYPED))
        memories = [s.memory for s in run.steps if s.memory]

        assert memories, "a refused confession left no trace"
        assert memories[0].importance > 0.8

    def test_a_rebuff_costs_relationship_rather_than_earning_it(self, narrator, director, session):
        intent = PlayerIntent(action="tease", target="aiko", risk=Risk.high, raw="you're hopeless")
        relationship(session, affection=10, trust=5, familiarity=8, anger=30)

        run = narrator.run(session, intent, directive=director.plan(session, intent, TYPED))
        deltas = [s.relationship_changes["aiko"] for s in run.steps if "aiko" in s.relationship_changes]

        assert deltas
        assert deltas[0].anger > 0 or deltas[0].trust < 0

    def test_without_a_directive_the_narrator_still_works(self, narrator, session):
        """The offline path must not depend on planning having happened."""
        run = narrator.run(session, PlayerIntent(action="talk_to", target="aiko", raw="hi"))
        assert run.steps and run.steps[-1].is_blocking


class TestImplicitTarget:
    """An unaddressed line should go to whoever the player was just talking to."""

    def test_it_follows_the_thread_of_the_conversation(self, director, session):
        from app.domain.story import DialogueLine

        session.world.present_characters = ["aiko", "ren", "haruto"]
        for index, speaker in enumerate(("haruto", "aiko")):
            session.steps.append(
                StoryStep(
                    **GeneratedStep(
                        type=StepType.dialogue,
                        location="classroom",
                        dialogue=DialogueLine(speaker=speaker, text="."),
                    ).model_dump(),
                    step_id=f"step_{index:05d}",
                    index=index,
                    batch_id="b",
                )
            )

        intent = director.parse_keywords(session, "I say sorry, that came out wrong")
        assert intent.action == "apologise"
        assert intent.target == "aiko", "the apology went to someone who was not in the conversation"

    def test_someone_who_has_left_the_scene_is_not_addressed(self, director, session):
        from app.domain.story import DialogueLine

        session.world.present_characters = ["ren"]
        session.steps.append(
            StoryStep(
                **GeneratedStep(
                    type=StepType.dialogue,
                    location="classroom",
                    dialogue=DialogueLine(speaker="haruto", text="."),
                ).model_dump(),
                step_id="step_00000",
                index=0,
                batch_id="b",
            )
        )
        assert director.parse_keywords(session, "I apologise").target == "ren"

    def test_an_explicit_name_always_wins(self, director, session):
        from app.domain.story import DialogueLine

        session.world.present_characters = ["aiko", "mika"]
        session.steps.append(
            StoryStep(
                **GeneratedStep(
                    type=StepType.dialogue,
                    location="classroom",
                    dialogue=DialogueLine(speaker="aiko", text="."),
                ).model_dump(),
                step_id="step_00000",
                index=0,
                batch_id="b",
            )
        )
        assert director.parse_keywords(session, "I apologise to Mika").target == "mika"

    def test_an_empty_room_has_no_target(self, director, session):
        session.world.present_characters = []
        assert director.parse_keywords(session, "I sigh").target is None

    @pytest.mark.parametrize(
        "text",
        [
            "I tell Aiko she is hopeless at this",
            "I say Aiko is useless at paperwork",
            "I make fun of Aiko's handwriting",
        ],
    )
    def test_the_tease_lexicon_covers_ordinary_needling(self, director, session, text):
        intent = director.parse_keywords(session, text)
        assert intent.action == "tease"
        assert intent.target == "aiko"
        assert intent.risk is Risk.high


class TestWorldClockAndArc:
    """Without these advancing, the arc guidance is a constant and every rooftop
    scene resolves to the same cached sunset."""

    def _service(self, world, tmp_path, steps_per_arc=3):
        from test_generation_service import Engine

        engine = Engine(world, tmp_path)
        engine.service.steps_per_arc = steps_per_arc
        return engine

    @pytest.mark.parametrize(
        ("text", "action", "destination"),
        [
            ("let's go to the rooftop", "move_location", "rooftop"),
            ("I head to the library", "move_location", "library"),
            ("let's go home", "move_location", "player_home"),
            ("I want to see the train station", "move_location", "train_station"),
        ],
    )
    def test_going_somewhere_parses_as_a_move(self, director, session, world, text, action, destination):
        intent = director.parse_keywords(session, text)
        assert intent.action == action, f"{text!r} did not read as a move"
        assert world.resolve_location(text) == destination

    def test_let_us_go_without_a_place_is_still_an_invitation(self, director, session):
        assert director.parse_keywords(session, "let's go, come with me").action == "invite_character"

    def test_a_move_emits_a_real_transition_step(self, narrator, session, director):
        intent = PlayerIntent(action="move_location", target=None, raw="let's go to the rooftop")
        run = narrator.run(session, intent, directive=director.plan(session, intent, TYPED))

        transitions = [s for s in run.steps if s.type is StepType.transition]
        assert transitions, "a move that emits no transition cannot move the clock"
        assert transitions[0].location == "rooftop"
        assert run.steps[-1].location == "rooftop"

    def test_a_directive_push_also_moves_the_scene(self, narrator, session, director):
        for index in range(20):
            append(session, index)
        intent = PlayerIntent(action="talk_to", target="aiko", raw="hi")
        plan = director.plan(session, intent, TYPED)
        assert plan.push_location

        run = narrator.run(session, intent, directive=plan)
        assert any(s.type is StepType.transition for s in run.steps)

    async def test_the_clock_only_moves_forward(self, world, tmp_path):
        from app.domain.enums import TIMES_OF_DAY

        engine = self._service(world, tmp_path)
        session = await engine.start(world)
        service = engine.service

        seen = [(session.world.day, session.world.time_of_day)]
        for location in ("rooftop", "library", "park", "train_station", "player_home", "classroom"):
            service._advance_clock(session, location)
            seen.append((session.world.day, session.world.time_of_day))

        for (day_a, time_a), (day_b, time_b) in zip(seen, seen[1:]):
            assert (day_b, TIMES_OF_DAY.index(time_b)) > (day_a, TIMES_OF_DAY.index(time_a)), (
                f"time went backwards: {day_a} {time_a} -> {day_b} {time_b}"
            )

    async def test_the_day_rolls_and_the_weekday_follows(self, world, tmp_path):
        engine = self._service(world, tmp_path)
        session = await engine.start(world)

        session.world.time_of_day = "night"
        session.world.day = 1
        session.world.weekday = "Monday"
        engine.service._advance_clock(session, "classroom")  # mornings only, so it rolls

        assert session.world.day == 2
        assert session.world.weekday == "Tuesday"
        assert session.world.time_of_day == "morning"

    async def test_the_clock_snaps_to_a_time_the_place_supports(self, world, tmp_path):
        engine = self._service(world, tmp_path)
        session = await engine.start(world)

        session.world.time_of_day = "morning"
        engine.service._advance_clock(session, "cafeteria")  # noon only
        assert session.world.time_of_day == "noon"

    async def test_the_arc_advances_and_records_what_it_left(self, world, tmp_path):
        engine = self._service(world, tmp_path, steps_per_arc=3)
        session = await engine.start(world)
        service = engine.service

        assert session.world.arc == "prologue"

        session.cursor = 3
        service._advance_arc(session)
        assert session.world.arc == world.arcs[1]
        assert "prologue" in session.world.completed_events

        session.cursor = 999
        service._advance_arc(session)
        assert session.world.arc == world.arcs[-1], "a long save should reach the last arc"

    async def test_the_arc_never_runs_off_the_end(self, world, tmp_path):
        engine = self._service(world, tmp_path, steps_per_arc=1)
        session = await engine.start(world)
        session.cursor = 10_000
        engine.service._advance_arc(session)
        assert session.world.arc in world.arcs

    def test_every_authored_arc_note_becomes_reachable(self, world, director, session):
        """Four of the five were unreachable while the arc never advanced."""
        for arc in world.arcs:
            session.world.arc = arc
            note = director.plan(session, PlayerIntent(action="talk_to"), TYPED).arc_note
            assert note, f"arc {arc!r} has no authored note"


class TestMoveVersusInvitation:
    """Both name a place and a movement verb; only one of them is a scene change."""

    @pytest.mark.parametrize(
        "text",
        [
            "I ask Aiko if she wants to walk home with me",
            "I ask Ren to come with me to the rooftop",
            "let's walk to the station together",
        ],
    )
    def test_asking_someone_along_is_an_invitation(self, director, session, text):
        assert director.parse_keywords(session, text).action == "invite_character"

    @pytest.mark.parametrize(
        "text",
        [
            "let's go home",
            "let's go to the rooftop",
            "I head to the library",
            "I want to see the train station",
            "I walk back to the classroom",
        ],
    )
    def test_going_somewhere_alone_is_a_move(self, director, session, text):
        session.world.location = "cafeteria"
        assert director.parse_keywords(session, text).action == "move_location"

    def test_naming_a_place_without_going_there_is_not_a_move(self, director, session):
        intent = director.parse_keywords(session, "I ask Aiko about the rooftop")
        assert intent.action == "ask_about"

    def test_going_where_you_already_are_emits_no_transition(self, director, narrator, session):
        """The label may still say move; what matters is that the scene does not
        transition to where it already is, which would spuriously advance the clock."""
        session.world.location = "rooftop"
        intent = director.parse_keywords(session, "let's go to the rooftop")
        run = narrator.run(session, intent, directive=director.plan(session, intent, TYPED))

        assert not [s for s in run.steps if s.type is StepType.transition]


class TestMovesAreNotOffers:
    def test_a_move_is_never_rebuffed(self, world, narrator, director, session):
        """Regression: refusing a move produced 'I'm fine, though' in reply to walking."""
        session.characters["aiko"].relationship.update({"trust": 2, "familiarity": 3, "anger": 40})
        intent = director.parse_keywords(session, "let's go to the rooftop")
        plan = director.plan(session, intent, TYPED)

        assert plan.allow_failure is True, "the stance really is unreceptive here"
        run = narrator.run(session, intent, directive=plan)

        assert "turned it down" not in run.summary
        lines = [s.dialogue.text for s in run.steps if s.dialogue]
        assert "I'm fine, though. Really." not in " ".join(lines)

    def test_observing_is_never_rebuffed_either(self, world, narrator, director, session):
        session.characters["aiko"].relationship.update({"trust": 2, "familiarity": 3})
        intent = PlayerIntent(action="observe", target="aiko", raw="I just watch")
        run = narrator.run(session, intent, directive=director.plan(session, intent, TYPED))
        assert "turned it down" not in run.summary

    def test_the_summary_names_where_they_are_going(self, director, session):
        session.world.location = "classroom"
        intent = director.parse_keywords(session, "let's go to the rooftop")
        assert "rooftop" in intent.summary

        intent = director.parse_keywords(session, "I head to the train station")
        assert "platform" in intent.summary, "should use the prose name, not the id"
