"""Who a story can become about, and how many people it can end with.

Two separate rules meet in ``agents/routes.py``: the cast a given player's story can be
romantic with, and the route the player chose at setup. The first is enforced in four
places -- the validator, the ending, the Director's brief and the offline narrator --
because a single unguarded path is the whole guarantee gone.
"""

from __future__ import annotations

import re

import pytest

from app.agents.ending import EndingKind, choose_ending, romance_partners
from app.agents.routes import (
    ROUTE_FLAG,
    note,
    open_routes,
    romance_candidates,
    settling_partner,
)
from app.domain.direction import DecisionContext, DecisionKind, Directive
from app.domain.enums import Route, StepType
from app.domain.intent import PlayerIntent
from app.domain.story import GeneratedRun, GeneratedStep, RelationshipDelta
from test_ending import met
from test_generation_service import engine  # noqa: F401 - fixture


def beat(**kwargs):
    return GeneratedStep(**{
        "type": "narration", "location": "classroom", "characters": ["aiko"],
        "narration": "Aiko squares the notebook against the edge of the table.", **kwargs,
    })


class TestWhoTheStoryCanBeAbout:
    @pytest.mark.parametrize(
        ("pronouns", "expected"),
        [
            ("he/him", {"aiko", "mika", "ren"}),
            ("she/her", {"haruto", "ren"}),
            ("they/them", {"aiko", "mika", "haruto", "ren"}),
            ("He/Him", {"aiko", "mika", "ren"}),
        ],
    )
    def test_the_cast_a_player_can_be_romantic_with(self, world, session, pronouns, expected):
        session.player.pronouns = pronouns
        assert set(romance_candidates(world, session.player)) == expected

    def test_the_writer_is_given_names_and_no_reason(self, world, session):
        session.player.pronouns = "he/him"
        line = note(world, session)

        assert "aiko" in line and "mika" in line and "haruto" not in line
        # The model paraphrases what it is told. It can only be given the names: a line
        # that explained itself would come back out of somebody's mouth.
        assert not re.search(r"\b(gender|boy|girl|man|woman|male|female|because|only)\b", line, re.IGNORECASE)

    def test_romance_cannot_grow_outside_them_but_warmth_can(self, validator, session):
        session.player.pronouns = "he/him"
        report = validator.validate(GeneratedRun(steps=[beat(relationship_changes={
            "haruto": RelationshipDelta(romance=4, affection=3, trust=2),
            "aiko": RelationshipDelta(romance=3, affection=2),
        })]), session)

        haruto = report.steps[0].relationship_changes["haruto"]
        assert haruto.romance == 0
        assert (haruto.affection, haruto.trust) == (3, 2), "warmth is not the engine's to refuse"
        assert report.steps[0].relationship_changes["aiko"].romance == 3

    def test_a_story_ends_as_a_friendship_with_someone_it_was_never_about(self, world, session):
        session.player.pronouns = "he/him"
        met(session, "haruto", romance=70, affection=70, trust=60)

        assert choose_ending(world, session) == (EndingKind.friendship, "haruto")
        assert romance_partners(world, session) == []

    def test_offline_a_confession_outside_them_is_answered_as_warmth(self, narrator, validator, session):
        session.player.pronouns = "he/him"
        met(session, "haruto", affection=40, trust=40, familiarity=40)
        intent = PlayerIntent(action="confess", target="haruto", raw="I tell Haruto how I feel",
                              summary="{player} tells Haruto the truth")

        report = validator.validate(narrator.run(session, intent, max_steps=6), session)

        assert report.steps, "the scene still happens"
        assert all(
            delta.romance == 0
            for step in report.steps
            for delta in step.relationship_changes.values()
        )


class TestSingleRoute:
    def test_it_settles_once_one_person_is_clearly_ahead(self, world, session):
        session.player.route = Route.single
        met(session, "aiko", romance=20)
        met(session, "mika", romance=18)
        assert settling_partner(world, session) is None, "a coin-flip lead is not a decision"

        session.characters["aiko"].relationship["romance"] = 40
        assert settling_partner(world, session) == "aiko"

    def test_what_it_settled_on_does_not_move_when_romance_dips(self, world, session):
        session.player.route = Route.single
        session.world.flags[ROUTE_FLAG] = "aiko"
        met(session, "aiko", romance=5)
        met(session, "mika", romance=60)

        assert open_routes(world, session) == {"aiko"}
        assert settling_partner(world, session) is None, "it is recorded, not recomputed"
        assert "aiko" in note(world, session) and "mika" not in note(world, session)

    def test_before_it_settles_every_door_is_open(self, world, session):
        session.player.route = Route.single
        assert open_routes(world, session) == set(romance_candidates(world, session.player))

    def test_a_named_interest_is_the_route_from_the_first_turn(self, world, session):
        session.player.route = Route.single
        session.player.romance_focus = "mika"
        assert open_routes(world, session) == {"mika"}

    def test_naming_someone_the_story_is_not_about_settles_nothing(self, world, session):
        """``romance_focus`` is a request the API accepts from anyone. It cannot open a
        route on its own -- it can only choose between the ones already open."""
        session.player.route = Route.single
        session.player.pronouns = "he/him"
        session.player.romance_focus = "haruto"
        met(session, "haruto", romance=70, affection=70, trust=60)

        assert open_routes(world, session) == {"aiko", "mika", "ren"}
        assert choose_ending(world, session) == (EndingKind.friendship, "haruto")
        assert romance_partners(world, session) == []

    async def test_the_engine_writes_it_into_the_save_on_delivery(self, engine):
        session = await engine.games.get("g1")
        session.player.route = Route.single
        met(session, "aiko", romance=40)
        await engine.games.save(session)

        await engine.service.submit_action("g1", "I tell Aiko the truth")
        await engine.generation.drain()
        await engine.service.next_batch("g1", limit=20)

        saved = await engine.games.get("g1")
        assert saved.world.flags[ROUTE_FLAG] == "aiko", "a route the save does not record is not a route"

    def test_it_ends_with_one_person(self, world, session):
        session.player.route = Route.single
        session.world.flags[ROUTE_FLAG] = "aiko"
        met(session, "aiko", romance=60, affection=65, trust=55)
        met(session, "mika", romance=55, affection=60, trust=50)

        assert choose_ending(world, session) == (EndingKind.romance, "aiko")
        assert romance_partners(world, session) == ["aiko"]


def test_every_brief_carries_the_names(world, session, director):
    session.player.pronouns = "she/her"
    directive = director.plan(session, PlayerIntent(action="talk_to"),
                              DecisionContext(kind=DecisionKind.free_text, typed="I say hello"))

    assert "Romance can develop with: ren, haruto" in directive.render()


class TestHaremRoute:
    def test_nothing_narrows_down(self, world, session):
        session.player.route = Route.harem
        session.world.flags[ROUTE_FLAG] = "aiko"
        assert open_routes(world, session) == set(romance_candidates(world, session.player))
        assert settling_partner(world, session) is None

    def test_it_ends_with_everyone_who_was_earned(self, world, session):
        session.player.route = Route.harem
        met(session, "aiko", romance=60, affection=65, trust=55)
        met(session, "mika", romance=55, affection=60, trust=40)
        met(session, "ren", friendship=45, trust=45)

        kind, partner = choose_ending(world, session)
        assert kind is EndingKind.romance
        assert romance_partners(world, session) == ["aiko", "mika"]
        assert partner == "aiko", "the finale still has somebody to centre on"

    def test_offline_the_finale_gives_each_of_them_their_own_line(self, narrator, validator, session):
        session.player.route = Route.harem
        met(session, "aiko", romance=60, affection=65, trust=55)
        met(session, "mika", romance=58, affection=60, trust=50)
        directive = Directive(is_finale=True, ending_kind="romance", ending_partner="aiko",
                              ending_partners=["aiko", "mika"])

        report = validator.validate(narrator.finale(session, directive), session, allow_ending=True)

        speakers = {step.dialogue.speaker for step in report.steps if step.dialogue}
        assert speakers == {"aiko", "mika"}
        assert report.steps[-1].type is StepType.ending

    def test_being_pleasant_to_everyone_is_not_a_harem(self, world, session):
        session.player.route = Route.harem
        met(session, "aiko", affection=14)
        met(session, "mika", affection=12)

        assert romance_partners(world, session) == []
        assert choose_ending(world, session)[0] is EndingKind.solo

    def test_the_finale_is_told_to_resolve_all_of_them(self, world, session, director):
        session.player.route = Route.harem
        session.cursor = 400
        met(session, "aiko", romance=60, affection=65, trust=55)
        met(session, "mika", romance=58, affection=60, trust=50)

        directive = director.plan(session, PlayerIntent(action="talk_to"),
                                  DecisionContext(kind=DecisionKind.free_text, typed="I stay"))

        assert directive.is_finale and directive.ending_partners == ["aiko", "mika"]
        assert "aiko, mika" in directive.render()


def test_a_save_written_before_routes_existed_plays_as_a_single_one(world, session):
    stored = session.player.model_dump()
    stored.pop("route")

    from app.domain.state import PlayerProfile

    assert PlayerProfile.model_validate(stored).route is Route.single
