"""The ending — PRD §16, and the gate that keeps it past 300 steps."""

from __future__ import annotations

import pytest

from app.agents.ending import ANGER_WEIGHT, EndingKind, choose_ending, growth_for
from app.domain.direction import DecisionContext, DecisionKind, Directive
from app.domain.enums import StepType
from app.domain.intent import PlayerIntent
from app.domain.story import Choice, DialogueLine, GeneratedRun, GeneratedStep


def run_of(*steps):
    return GeneratedRun(steps=list(steps))


def met(session, character_id, **relationship):
    state = session.characters[character_id]
    state.met = True
    state.relationship.update(relationship)
    return session


class TestEndingSelection:
    def test_a_player_who_engaged_with_nobody_ends_alone(self, world, session):
        assert choose_ending(world, session) == (EndingKind.solo, None)

    def test_merely_meeting_someone_is_not_a_relationship(self, world, session):
        met(session, "ren", familiarity=60)
        assert choose_ending(world, session)[0] is EndingKind.solo

    def test_romance_beats_friendship_when_it_grew_more(self, world, session):
        met(session, "aiko", romance=60, affection=65, trust=55)
        assert choose_ending(world, session) == (EndingKind.romance, "aiko")

    def test_friendship_when_that_is_what_grew(self, world, session):
        met(session, "ren", friendship=70, trust=60)
        assert choose_ending(world, session) == (EndingKind.friendship, "ren")

    def test_growth_is_measured_against_the_authored_baseline(self, world, session):
        """Ren opens at friendship 25; Aiko at 0. Absolute thresholds would hand a
        passive player a Ren ending and punish someone who worked on Aiko."""
        met(session, "ren", friendship=30, trust=20)
        met(session, "aiko", friendship=30, trust=20)

        assert growth_for(world, session, "aiko")[0] > growth_for(world, session, "ren")[0]
        assert choose_ending(world, session)[1] == "aiko"

    def test_you_do_not_get_a_love_story_with_someone_furious_at_you(self, world, session):
        met(session, "aiko", romance=70, affection=70, anger=60)
        assert choose_ending(world, session)[0] is EndingKind.solo

        met(session, "aiko", anger=5)
        assert choose_ending(world, session)[0] is EndingKind.romance

    def test_anger_is_weighted_more_than_a_single_point_of_growth(self):
        assert ANGER_WEIGHT >= 2

    def test_a_tie_goes_to_the_romance_chosen_at_setup(self, world, session):
        met(session, "aiko", friendship=50, trust=42)
        met(session, "mika", friendship=62, trust=54)
        assert growth_for(world, session, "aiko")[0] == growth_for(world, session, "mika")[0]

        session.player.romance_focus = "aiko"
        assert choose_ending(world, session)[1] == "aiko"
        session.player.romance_focus = "mika"
        assert choose_ending(world, session)[1] == "mika"

    def test_selection_is_deterministic(self, world, session):
        met(session, "aiko", romance=40, affection=40)
        met(session, "haruto", friendship=40, trust=40)
        assert choose_ending(world, session) == choose_ending(world, session)


class TestTheGate:
    def _plan(self, world, session, *, cursor, kind=DecisionKind.free_text, minimum=300):
        from app.agents.director import DirectorAgent

        session.cursor = cursor
        return DirectorAgent(world, ending_min_steps=minimum).plan(
            session, PlayerIntent(action="talk_to", target="aiko"), DecisionContext(kind=kind)
        )

    def test_the_story_cannot_end_early(self, world, session):
        assert self._plan(world, session, cursor=298).is_finale is False

    def test_it_takes_more_than_the_threshold_not_exactly_it(self, world, session):
        assert self._plan(world, session, cursor=299).is_finale is False  # 300 delivered
        assert self._plan(world, session, cursor=300).is_finale is True  # 301 delivered

    def test_a_story_never_ends_while_the_player_is_idle(self, world, session):
        """The ending should answer something they did, not time out on them."""
        assert self._plan(world, session, cursor=999, kind=DecisionKind.auto).is_finale is False

    def test_an_ended_game_does_not_end_again(self, world, session):
        session.ended = True
        assert self._plan(world, session, cursor=999).is_finale is False

    def test_the_finale_carries_its_kind_and_partner(self, world, session):
        met(session, "aiko", romance=60, affection=65, trust=55)
        directive = self._plan(world, session, cursor=400)

        assert directive.is_finale is True
        assert (directive.ending_kind, directive.ending_partner) == ("romance", "aiko")
        assert directive.push_location is None, "do not move the scene for the last run"
        assert directive.allow_failure is False, "the ending is not an attempt that can fail"

    def test_the_finale_direction_tells_the_writer_to_close(self, world, session):
        from app.agents.prompts import build_run_prompt

        directive = self._plan(world, session, cursor=400)
        prompt = build_run_prompt(
            world, session, PlayerIntent(action="talk_to", raw="x"), [],
            history_steps=6, decision=DecisionContext(kind=DecisionKind.free_text, typed="x"),
            directive=directive, max_steps=5,
        )
        assert "FINAL RUN" in prompt
        assert "do NOT offer the player" in prompt


class TestTheModelCannotEndTheStory:
    def test_ending_is_absent_from_the_wire_schema(self):
        from app.llm.dto import LLMRun
        from app.llm.schema import strict_schema

        step_type = strict_schema(LLMRun)["$defs"]["LLMStep"]["properties"]["type"]
        assert "ending" not in str(step_type)
        assert set(step_type["enum"]) == {
            "narration", "dialogue", "transition", "event", "choice", "prompt"
        }

    def test_an_unsanctioned_ending_step_is_demoted(self, validator, session):
        report = validator.validate(
            run_of(GeneratedStep(type="ending", location="classroom", narration="The end.")),
            session,
        )
        assert report.steps[0].type is StepType.narration
        assert report.steps[-1].is_blocking, "the story must carry on"
        assert any(v.rule == "run_structure" for v in report.violations)

    def test_the_ending_marker_cannot_be_forged_through_flags(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="narration",
                    location="classroom",
                    narration="Nothing to see here.",
                    flags_set={"ending": "romance", "ending_partner": "aiko", "ok_flag": "1"},
                )
            ),
            session,
        )
        assert report.steps[0].flags_set == {"ok_flag": "1"}
        assert sum(v.detail.startswith("reserved flag") for v in report.violations) == 2

    def test_a_step_cannot_set_unlimited_flags(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="narration", location="classroom", narration=".",
                    flags_set={f"flag_{i}": "1" for i in range(12)},
                )
            ),
            session,
        )
        assert len(report.steps[0].flags_set) <= 3


class TestValidatorPromotesTheFinale:
    def test_the_last_step_becomes_the_ending(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(type="narration", location="classroom", narration="The year closes."),
                GeneratedStep(
                    type="dialogue", location="classroom",
                    dialogue=DialogueLine(speaker="aiko", text="Then I'll see you."),
                ),
            ),
            session,
            allow_ending=True,
        )
        assert report.steps[-1].type is StepType.ending
        assert report.steps[-1].is_terminal
        assert not report.steps[-1].is_blocking

    def test_a_decision_point_on_the_final_run_is_dropped(self, validator, session):
        """Models staple a menu on out of habit; there is nothing after the end."""
        report = validator.validate(
            run_of(
                GeneratedStep(type="narration", location="classroom", narration="The year closes."),
                GeneratedStep(
                    type="choice", location="classroom",
                    next_choices=[Choice(id="a", text="Stay."), Choice(id="b", text="Go.")],
                ),
            ),
            session,
            allow_ending=True,
        )
        assert len(report.steps) == 1
        assert report.steps[0].type is StepType.ending
        assert report.steps[0].next_choices == []

    def test_no_free_text_terminator_is_stapled_on(self, validator, session):
        report = validator.validate(
            run_of(GeneratedStep(type="narration", location="classroom", narration="Fin.")),
            session,
            allow_ending=True,
        )
        assert [s.type for s in report.steps] == [StepType.ending]

    def test_an_epilogue_may_describe_what_the_player_does(self, validator, session):
        """Rule 1 protects a decision not yet made. The ending has no next decision, and
        _AGENCY_VERBS covers exactly the verbs an ending is made of."""
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="ending", location="classroom",
                    narration="You promise to write. You leave before anyone can say otherwise.",
                )
            ),
            session,
            allow_ending=True,
        )
        assert "You promise to write." in (report.steps[-1].narration or "")
        assert not any(v.rule == "player_agency" for v in report.violations)

    def test_a_model_written_ending_keeps_its_epilogue(self, validator, session):
        """The bug this replaces: the exemption was scoped to ``type is ending``, but the
        model cannot emit that type -- its ending arrives as narration and is promoted
        only after the loop, so the loop had already stripped it. An epilogue reading
        'You promise to write. The gate closes behind you.' came out with the first
        sentence deleted.
        """
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="narration", location="classroom",
                    narration="You promise to write. The gate closes behind you.",
                )
            ),
            session,
            allow_ending=True,
        )
        assert "You promise to write." in (report.steps[-1].narration or "")
        assert not any(v.rule == "player_agency" for v in report.violations)

    def test_the_whole_final_run_is_exempt_from_rule_one(self, validator, session):
        """Rule 1 protects a decision not yet made. In the final run there is no next
        decision at any point, so it protects nothing anywhere in it."""
        report = validator.validate(
            run_of(
                GeneratedStep(type="narration", location="classroom",
                              narration="You agree to everything. The bell goes."),
                GeneratedStep(type="narration", location="classroom", narration="Fin."),
            ),
            session,
            allow_ending=True,
        )
        assert "You agree to everything." in (report.steps[0].narration or "")

    def test_rule_one_still_applies_to_every_ordinary_run(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(type="narration", location="classroom",
                              narration="You agree to everything. The bell goes."),
            ),
            session,
        )
        assert "You agree" not in (report.steps[0].narration or "")

    def test_unsafe_content_still_stops_the_final_run(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(type="narration", location="classroom", narration="A fine close."),
                GeneratedStep(type="narration", location="classroom",
                              narration="Then an explicit sex scene."),
            ),
            session,
            allow_ending=True,
        )
        assert all("explicit" not in (s.narration or "") for s in report.steps)


class TestScriptedFinale:
    @pytest.mark.parametrize("kind", ["romance", "friendship", "solo"])
    def test_every_ending_kind_can_be_written_offline(self, narrator, session, kind):
        run = narrator.finale(
            session,
            Directive(is_finale=True, ending_kind=kind, ending_partner="aiko" if kind != "solo" else None),
        )
        assert run.steps[-1].type is StepType.ending
        assert run.steps[-1].narration
        assert not any(s.is_blocking for s in run.steps)

    def test_the_finale_is_deterministic(self, narrator, session):
        directive = Directive(is_finale=True, ending_kind="romance", ending_partner="aiko")
        first = narrator.finale(session, directive)
        second = narrator.finale(session, directive)
        assert [s.narration for s in first.steps] == [s.narration for s in second.steps]

    def test_the_partner_speaks_in_their_own_voice(self, narrator, session):
        run = narrator.finale(
            session, Directive(is_finale=True, ending_kind="romance", ending_partner="haruto")
        )
        speakers = {s.dialogue.speaker for s in run.steps if s.dialogue}
        assert speakers == {"haruto"}


class TestEndingEdges:
    def test_a_blank_option_costs_the_option_not_the_run(self):
        """Choice rejects empty text, so one stray blank used to raise out of
        LLMRun.model_validate and lose the whole generated run to the fallback."""
        from app.llm.dto import LLMRun

        run = LLMRun.model_validate(
            {
                "summary": "",
                "steps": [
                    {
                        "type": "choice", "location": "classroom", "characters": [],
                        "narration": None, "dialogue": None, "emotions": [],
                        "relationship_changes": [], "flags_set": [], "memory": None,
                        "visual": None,
                        "next_choices": [
                            {"id": "a", "text": "Real option."},
                            {"id": "b", "text": "   "},
                        ],
                    }
                ],
            }
        ).to_domain()

        assert [c.text for c in run.steps[0].next_choices] == ["Real option."]

    def test_a_character_the_world_forgot_cannot_win_the_ending(self, world, session):
        """No authored baseline means growth measured from zero, which would crown a
        leftover from an older version of the world."""
        from app.domain.state import CharacterState

        session.characters["ghost"] = CharacterState(
            id="ghost", name="Ghost", met=True,
            relationship={"romance": 90, "affection": 90},
        )
        met(session, "aiko", friendship=45, trust=45)

        kind, partner = choose_ending(world, session)
        assert partner == "aiko"

    async def test_a_second_ending_is_never_queued_behind_the_first(self, world, tmp_path):
        """Accepting another turn while the finale is queued generates an ending nobody
        will ever see."""
        from test_generation_service import TYPED, Engine

        engine = Engine(world, tmp_path)
        session = await engine.start(world)
        session.steps.append(
            __import__("app.domain.story", fromlist=["StoryStep"]).StoryStep(
                **GeneratedStep(type="ending", location="classroom", narration="The end.").model_dump(),
                step_id="step_00000", index=0, batch_id="b",
            )
        )
        session.cursor = -1  # queued, not yet delivered
        await engine.games.save(session)

        assert await engine.generation.submit(
            "g1", PlayerIntent(action="talk_to", raw="hi"), decision=TYPED
        ) is None
        await engine.generation.shutdown()

    async def test_a_batch_is_discarded_if_the_story_ended_first(self, world, tmp_path):
        from test_generation_service import TYPED, Engine

        engine = Engine(world, tmp_path)
        session = await engine.start(world)
        await engine.generation.submit("g1", PlayerIntent(action="talk_to", raw="hi"), decision=TYPED)

        ended = await engine.games.get("g1")
        ended.ended = True
        await engine.games.save(ended)

        await engine.generation.drain()
        assert (await engine.games.get("g1")).steps == [], "a finished story grew new steps"
        await engine.generation.shutdown()
