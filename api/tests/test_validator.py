"""PRD §24 — the five hard rules, and the repair-then-truncate policy around them."""

from __future__ import annotations

import pytest

from app.agents.validator import strip_agency
from app.domain.enums import StepType
from app.domain.story import (
    Choice,
    DialogueLine,
    GeneratedRun,
    GeneratedStep,
    RelationshipDelta,
)


def run_of(*steps: GeneratedStep) -> GeneratedRun:
    return GeneratedRun(steps=list(steps))


class TestRule1PlayerAgency:
    def test_narration_that_decides_for_the_player_is_stripped(self):
        kept, removed = strip_agency("The wind picks up. You agree to go with her.")
        assert kept == "The wind picks up."
        assert removed is True

    @pytest.mark.parametrize(
        "text",
        [
            "You feel the cold coming off the window.",
            "You can see the whole town from up here.",
            "You are still holding the handouts.",
        ],
    )
    def test_involuntary_perception_is_left_alone(self, text):
        kept, removed = strip_agency(text)
        assert kept == text
        assert removed is False

    def test_dialogue_spoken_by_the_player_truncates_the_run(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(type="narration", location="classroom", narration="Aiko waits."),
                GeneratedStep(
                    type="dialogue",
                    location="classroom",
                    dialogue=DialogueLine(speaker="player", text="Yes, I promise."),
                ),
                GeneratedStep(type="narration", location="classroom", narration="Never reached."),
            ),
            session,
        )
        assert [step.narration for step in report.steps if step.narration] == ["Aiko waits."]
        assert any(v.rule == "player_agency" and v.remedy == "truncated" for v in report.violations)


class TestRule3WorldConsistency:
    def test_unknown_location_snaps_back(self, validator, session):
        report = validator.validate(
            run_of(GeneratedStep(type="narration", location="mars_base", narration="Odd.")),
            session,
        )
        assert report.steps[0].location == "classroom"
        assert any(v.rule == "world_consistency" for v in report.violations)

    def test_teleport_without_a_transition_is_reverted(self, validator, session):
        report = validator.validate(
            run_of(GeneratedStep(type="dialogue", location="park", dialogue=DialogueLine(speaker="aiko", text="Hi."))),
            session,
        )
        assert report.steps[0].location == "classroom"

    def test_an_explicit_transition_moves_the_scene(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(type="transition", location="rooftop", narration="The roof door bangs open."),
                GeneratedStep(type="dialogue", location="rooftop", dialogue=DialogueLine(speaker="aiko", text="You came.")),
            ),
            session,
        )
        assert [step.location for step in report.steps[:2]] == ["rooftop", "rooftop"]
        assert not any(v.rule == "world_consistency" for v in report.violations)


class TestRule4StateConsistency:
    def test_oversized_deltas_are_clamped_not_rejected(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="narration",
                    location="classroom",
                    narration="Something enormous happens.",
                    relationship_changes={"aiko": RelationshipDelta(affection=60, trust=-40)},
                )
            ),
            session,
        )
        delta = report.steps[0].relationship_changes["aiko"]
        assert (delta.affection, delta.trust) == (5, -5)
        assert any(v.remedy == "clamped" for v in report.violations)

    def test_deltas_for_unknown_characters_are_dropped(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="narration",
                    location="classroom",
                    narration="A stranger.",
                    relationship_changes={"godzilla": RelationshipDelta(affection=2)},
                )
            ),
            session,
        )
        assert report.steps[0].relationship_changes == {}


class TestRunStructure:
    def test_every_run_ends_at_a_decision_point(self, validator, session):
        report = validator.validate(
            run_of(GeneratedStep(type="narration", location="classroom", narration="A quiet beat.")),
            session,
        )
        assert report.steps[-1].is_blocking

    def test_steps_after_the_first_decision_point_are_discarded(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="choice",
                    location="classroom",
                    next_choices=[Choice(id="a", text="Stay."), Choice(id="b", text="Go.")],
                ),
                GeneratedStep(type="narration", location="classroom", narration="Discarded."),
            ),
            session,
        )
        assert len(report.steps) == 1
        assert any(v.remedy == "truncated" for v in report.violations)

    def test_duplicate_choices_are_removed_and_ids_renumbered(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="choice",
                    location="classroom",
                    next_choices=[
                        Choice(id="zzz", text="I promised."),
                        Choice(id="yyy", text="i promised!"),  # same option, different punctuation
                        Choice(id="xxx", text="You sounded like you needed someone."),
                    ],
                )
            ),
            session,
        )
        texts = [c.text for c in report.steps[0].next_choices]
        assert texts[:2] == ["I promised.", "You sounded like you needed someone."]
        assert [c.id for c in report.steps[0].next_choices] == ["choice_1", "choice_2", "choice_3"]


class TestChoiceCount:
    """Every decision point offers between MIN_CHOICES and MAX_CHOICES options."""

    def test_a_short_list_is_topped_up_rather_than_taken_away(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="choice",
                    location="classroom",
                    characters=["aiko"],
                    next_choices=[Choice(id="a", text="Only one.")],
                )
            ),
            session,
        )
        step = report.steps[-1]

        assert step.type is StepType.choice, "a short list must not cost the player the menu"
        assert len(step.next_choices) == validator.min_choices
        assert step.next_choices[0].text == "Only one.", "the model's own option comes first"
        assert any(v.remedy == "rewritten" for v in report.violations)

    def test_top_ups_name_the_character_in_the_scene(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="choice",
                    location="classroom",
                    dialogue=None,
                    characters=["aiko"],
                    next_choices=[Choice(id="a", text="Only one.")],
                )
            ),
            session,
        )
        filler = " ".join(c.text for c in report.steps[-1].next_choices[1:])
        assert "Aiko" in filler

    def test_top_ups_stay_generic_when_nobody_is_named(self, validator, session):
        report = validator.validate(
            run_of(GeneratedStep(type="choice", location="classroom", next_choices=[])),
            session,
        )
        assert len(report.steps[-1].next_choices) == validator.min_choices
        assert all("{" not in c.text for c in report.steps[-1].next_choices)

    def test_an_over_long_list_is_capped(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="choice",
                    location="classroom",
                    next_choices=[Choice(id=f"c{i}", text=f"Option {i}.") for i in range(9)],
                )
            ),
            session,
        )
        assert len(report.steps[-1].next_choices) == validator.max_choices
        assert any(v.remedy == "truncated" for v in report.violations)

    def test_a_list_already_in_range_is_left_alone(self, validator, session):
        texts = ["I promised.", "You sounded like you needed someone.", "Don't read into it."]
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="choice",
                    location="classroom",
                    next_choices=[Choice(id=f"x{i}", text=t) for i, t in enumerate(texts)],
                )
            ),
            session,
        )
        assert [c.text for c in report.steps[-1].next_choices] == texts
        assert not [v for v in report.violations if v.rule == "run_structure"]

    def test_top_ups_never_duplicate_what_the_model_offered(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(
                    type="choice",
                    location="classroom",
                    characters=["aiko"],
                    next_choices=[Choice(id="a", text="Say nothing, and let Aiko fill the silence.")],
                )
            ),
            session,
        )
        texts = [c.text for c in report.steps[-1].next_choices]
        assert len(texts) == len(set(texts))

    def test_topping_up_is_deterministic(self, validator, session):
        """Speculative prefetch keys branches by choice id, so the same step must
        always produce the same options."""
        def once():
            report = validator.validate(
                run_of(
                    GeneratedStep(
                        type="choice", location="classroom", characters=["aiko"],
                        next_choices=[Choice(id="a", text="Only one.")],
                    )
                ),
                session,
            )
            return [(c.id, c.text) for c in report.steps[-1].next_choices]

        assert once() == once()

    def test_an_explicit_prompt_step_is_still_legal(self, validator, session):
        """Free text stays a deliberate mode; it just stops being the consolation prize."""
        report = validator.validate(
            run_of(GeneratedStep(type="prompt", location="classroom", narration="Well?")),
            session,
        )
        assert report.steps[-1].type is StepType.prompt
        assert report.steps[-1].next_choices == []

    def test_the_run_is_capped_at_max_steps(self, validator, session):
        report = validator.validate(
            run_of(
                *[
                    GeneratedStep(type="narration", location="classroom", narration=f"Beat {i}.")
                    for i in range(25)
                ]
            ),
            session,
        )
        assert len(report.steps) <= validator.max_steps + 1  # +1 for the appended terminator


class TestContentSafety:
    def test_unsafe_output_cuts_the_run_at_that_step(self, validator, session):
        report = validator.validate(
            run_of(
                GeneratedStep(type="narration", location="classroom", narration="A fine sentence."),
                GeneratedStep(type="narration", location="classroom", narration="Then an explicit sex scene."),
            ),
            session,
        )
        assert all("explicit" not in (step.narration or "") for step in report.steps)
        assert any(v.rule == "content_safety" for v in report.violations)
