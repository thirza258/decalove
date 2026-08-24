"""What the model is actually shown — PRD §23."""

from __future__ import annotations

from app.agents.prompts import (
    build_context,
    build_intent_prompt,
    build_run_prompt,
    build_system_prompt,
)
from app.domain.direction import DecisionContext, DecisionKind, Directive, Pacing, Stance
from app.domain.enums import Risk
from app.domain.intent import PlayerIntent
from app.domain.memory import MemoryRecord
from app.domain.story import Choice, DialogueLine, GeneratedStep, StoryStep


def step(index, **overrides):
    base = {"type": "narration", "location": "classroom", "narration": f"Beat {index}."}
    base.update(overrides)
    return StoryStep(
        **GeneratedStep(**base).model_dump(), step_id=f"step_{index:05d}", index=index, batch_id="b"
    )


class TestSystemPrompt:
    def test_it_carries_the_rules_the_validator_enforces(self, world):
        prompt = build_system_prompt(world, max_steps=10, max_delta=5, rating="teen")

        for heading in ("PLAYER AGENCY", "CHARACTER CONSISTENCY", "WORLD CONSISTENCY",
                        "STATE CONSISTENCY", "CONTINUITY", "OUTPUT CONTRACT"):
            assert heading in prompt

        assert "never larger than 5" in prompt, "the delta cap must match the validator's"
        assert "between 3 and 10 steps" in prompt

    def test_it_lists_every_legal_location_and_expression(self, world):
        prompt = build_system_prompt(world, max_steps=10, max_delta=5, rating="teen")

        for location in world.locations:
            assert location.id in prompt
        for character in world.characters:
            assert character.id in prompt
            for expression in character.expressions:
                assert expression in prompt

    def test_content_boundaries_come_from_the_world(self, world):
        prompt = build_system_prompt(world, max_steps=10, max_delta=5, rating="teen")
        assert "CONTENT BOUNDARIES (teen)" in prompt
        for line in world.safety:
            assert line in prompt

    def test_it_forbids_writing_the_player_as_a_speaker(self, world):
        prompt = build_system_prompt(world, max_steps=10, max_delta=5, rating="teen")
        assert 'speaker "player"' in prompt


class TestContext:
    def test_an_empty_session_reads_cleanly(self, world, session):
        session.characters = {}
        context = build_context(world, session, [], history_steps=10)

        assert "(nobody met yet)" in context
        assert "(none yet)" in context
        assert "(the story has not started)" in context
        assert "Inventory: (empty)" in context

    def test_it_renders_state_memories_and_recent_beats(self, world, session):
        session.characters["aiko"].met = True
        session.characters["aiko"].relationship["affection"] = 42
        session.world.flags["festival_invited"] = True
        session.world.inventory.append("a borrowed umbrella")
        session.steps = [
            step(0),
            step(1, type="dialogue", dialogue=DialogueLine(speaker="aiko", text="You came.")),
            step(2, type="choice", next_choices=[Choice(id="a", text="I promised."), Choice(id="b", text="Barely.")]),
        ]
        session.history.append("Kai walked Aiko home.")

        context = build_context(
            world,
            session,
            [MemoryRecord(id="m", game_id=session.id, character="aiko",
                          text="Kai defended Aiko", importance=0.9, emotion="gratitude")],
            history_steps=10,
        )

        assert "affection 42" in context
        assert "festival_invited=True" in context
        assert "a borrowed umbrella" in context
        assert "Kai defended Aiko" in context and "(gratitude)" in context
        assert "importance 0.90" in context
        assert 'aiko: "You came."' in context
        assert "(offered: I promised. | Barely.)" in context
        assert "Kai walked Aiko home." in context

    def test_history_is_windowed(self, world, session):
        session.steps = [step(i) for i in range(30)]
        context = build_context(world, session, [], history_steps=5)

        assert "[29]" in context, "the newest beat must always be shown"
        assert "[25]" in context, "five steps means 25..29"
        assert "[24]" not in context

    def test_a_silent_step_still_renders(self, world, session):
        session.steps = [step(0, narration=None, type="event", flags_set={"x": "1"})]
        assert "(silence)" in build_context(world, session, [], history_steps=5)


class TestRunPrompt:
    """The per-turn prompt has to actually differ per turn -- that is its whole job."""

    def run_prompt(self, world, session, intent, decision, directive=None, **kwargs):
        return build_run_prompt(
            world,
            session,
            intent,
            [],
            history_steps=6,
            decision=decision,
            directive=directive or Directive(),
            max_steps=kwargs.get("max_steps", 10),
        )

    def test_a_typed_action_shows_the_words_and_asks_for_their_specifics(self, world, session):
        intent = PlayerIntent(
            action="invite_character", target="aiko", emotion="nervous",
            risk=Risk.medium, summary="Kai tries to invite Aiko along",
            raw="I ask Aiko to walk home with me",
        )
        decision = DecisionContext(
            kind=DecisionKind.free_text, typed="I ask Aiko to walk home with me"
        )
        prompt = self.run_prompt(world, session, intent, decision)

        assert 'wrote, in their own words: "I ask Aiko to walk home with me"' in prompt
        assert "honour its specifics" in prompt
        assert "action=invite_character, target=aiko" in prompt
        assert "Kai tries to invite Aiko along" in prompt
        assert "Return at most 10 steps." in prompt

    def test_a_chosen_option_names_what_they_turned_down(self, world, session):
        """The rejected options are signal; most engines throw them away."""
        decision = DecisionContext(
            kind=DecisionKind.choice,
            chosen_text="I promised I would.",
            rejected=["You sounded like you needed someone.", "Don't read into it."],
        )
        prompt = self.run_prompt(world, session, PlayerIntent(action="talk_to", raw=""), decision)

        assert 'The player chose: "I promised I would."' in prompt
        assert "passed on:" in prompt
        assert "You sounded like you needed someone." in prompt
        assert "Don't read into it." in prompt
        assert "wrote, in their own words" not in prompt

    def test_writing_instead_of_picking_is_called_out(self, world, session):
        decision = DecisionContext(
            kind=DecisionKind.free_text,
            typed="I ask about her brother",
            used_free_text_when_offered_choices=True,
        )
        prompt = self.run_prompt(world, session, PlayerIntent(action="ask_about", raw="x"), decision)
        assert "the menu did not contain" in prompt

    def test_an_unprompted_continuation_asks_for_restraint(self, world, session):
        prompt = self.run_prompt(
            world,
            session,
            PlayerIntent(action="observe", raw=""),
            DecisionContext(kind=DecisionKind.auto),
        )
        assert "No input from the player" in prompt
        assert "Do not introduce a new development" in prompt

    def test_the_directive_carries_pacing_stance_and_permission_to_fail(self, world, session):
        directive = Directive(
            pacing=Pacing.charged,
            tension=81,
            focus=["aiko", "ren"],
            stances=[
                Stance(character="aiko", posture="guarded", note="trust 18 -- deflects",
                       conflict_mode="serious", receptive=False)
            ],
            beat_goal="this is the beat that costs something",
            allow_failure=True,
            push_location="rooftop",
            arc_note="the festival is close",
            style_note="This player goes for the risky, direct thing.",
        )
        prompt = self.run_prompt(
            world, session, PlayerIntent(action="confess", risk=Risk.high, raw="x"),
            DecisionContext(kind=DecisionKind.free_text, typed="x"), directive,
        )

        assert "Pacing: charged (tension 81/100)" in prompt
        assert "this is the beat that costs something" in prompt
        assert "Carry it with: aiko, ren" in prompt
        assert "trust 18 -- deflects" in prompt
        assert "conflict reads as: serious" in prompt
        assert "allowed to fall flat" in prompt
        assert "Move it to rooftop" in prompt
        assert "the festival is close" in prompt
        assert "risky, direct thing" in prompt

    def test_a_landing_attempt_says_so_instead(self, world, session):
        prompt = self.run_prompt(
            world, session, PlayerIntent(action="talk_to", raw="x"),
            DecisionContext(kind=DecisionKind.free_text, typed="x"),
            Directive(allow_failure=False),
        )
        assert "The attempt should land" in prompt
        assert "allowed to fall flat" not in prompt

    def test_the_same_input_at_different_relationships_yields_different_prompts(self, world, session):
        """PRD §15, at the prompt level."""
        from app.agents.director import DirectorAgent

        intent = PlayerIntent(action="tease", target="aiko", risk=Risk.high, raw="I tease Aiko")
        decision = DecisionContext(kind=DecisionKind.free_text, typed="I tease Aiko")
        director = DirectorAgent(world)

        session.characters["aiko"].relationship.update({"affection": 60, "trust": 55, "familiarity": 40})
        warm = self.run_prompt(world, session, intent, decision, director.plan(session, intent, decision))

        session.characters["aiko"].relationship.update({"affection": 20, "trust": 10, "familiarity": 40})
        cold = self.run_prompt(world, session, intent, decision, director.plan(session, intent, decision))

        assert warm != cold
        assert "comfortable enough to tease" in warm
        assert "guarded" in cold
        assert "conflict reads as: playful" in warm
        assert "conflict reads as: serious" in cold


class TestPlaceholders:
    def test_the_player_placeholder_never_reaches_the_model(self, world, session):
        """The keyword parser writes summaries containing {player}; the scripted
        narrator expands it, and the prompt path has to as well."""
        session.history.append("{player} tries to invite Aiko along — Aiko turned it down.")
        intent = PlayerIntent(
            action="tease", target="aiko", risk=Risk.high,
            summary="{player} tries to get under Aiko's skin", raw="x",
        )
        prompt = build_run_prompt(
            world, session, intent, [], history_steps=6,
            decision=DecisionContext(kind=DecisionKind.free_text, typed="x"),
            directive=Directive(), max_steps=10,
        )

        assert "{player}" not in prompt
        assert "Kai tries to get under Aiko's skin" in prompt
        assert "Kai tries to invite Aiko along" in prompt

    def test_a_summary_with_stray_braces_does_not_break_the_turn(self, world, session):
        intent = PlayerIntent(action="talk_to", summary="they said {something odd}", raw="x")
        prompt = build_run_prompt(
            world, session, intent, [], history_steps=6,
            decision=DecisionContext(kind=DecisionKind.free_text, typed="x"),
            directive=Directive(), max_steps=10,
        )
        assert "something odd" in prompt


class TestIntentPrompt:
    def test_it_scopes_the_parse_to_the_cast_and_scene(self, world, session):
        prompt = build_intent_prompt(world, session, "I wave at Aiko")

        assert "I wave at Aiko" in prompt
        assert "aiko (Aiko Serizawa)" in prompt
        assert "PRESENT RIGHT NOW: aiko, ren" in prompt
        assert "LOCATION: classroom" in prompt
        assert "never the outcome" in prompt

    def test_an_empty_scene_still_renders(self, world, session):
        session.world.present_characters = []
        assert "PRESENT RIGHT NOW: nobody" in build_intent_prompt(world, session, "hello")
