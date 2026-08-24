"""A whole playthrough, start to ending.

This is the one test that exercises the shape of the product rather than a piece of it:
the story runs for more than 300 delivered steps, every decision point along the way
offers a real menu, the world clock and the arcs move, and it finishes with an ending
rather than running forever.

It plays the game for real over HTTP against the offline seams, so it needs no key, no
database and no Ren'Py.
"""

from __future__ import annotations

import time

import pytest

from app.config import settings

pytestmark = pytest.mark.slow

INPUTS = [
    "I ask Aiko about the council paperwork",
    "I tell Ren their sketch is better than they think",
    "let's go to the rooftop",
    "I ask Mika how her knee is holding up",
    "I help Haruto reshelve the returns",
    "I say sorry for earlier",
    "let's head to the cafeteria",
    "I ask what everyone is doing for the festival",
    "I tell Aiko she does not have to carry all of it",
    "let's go to the park",
]


def play_until_decision(client, game_id, transcript, budget=60):
    """Deliver steps until the game hands control back. Returns the decision step."""
    for _ in range(budget):
        body = client.get(
            f"/api/v1/games/{game_id}/steps/next", params={"wait_ms": 4000}
        ).json()
        status = body["status"]

        if status == "ready":
            transcript.append(body["step"])
            step = body["step"]
            if step["type"] in ("choice", "prompt"):
                return step
            if step["type"] == "ending":
                return None
            continue
        if status == "awaiting_player":
            return body["step"]
        if status == "ended":
            return None
        assert status == "pending"
    raise AssertionError("never reached a decision point")


@pytest.fixture
def transcript():
    return []


class TestAWholePlaythrough:
    def test_the_story_runs_past_three_hundred_steps_and_then_ends(self, client, transcript):
        started = time.monotonic()
        game_id = client.post(
            "/api/v1/games",
            json={"player_name": "Kai", "pronouns": "he/him", "romance_focus": "aiko"},
        ).json()["game_id"]

        decisions = 0
        ended = False

        for turn in range(400):
            decision = play_until_decision(client, game_id, transcript)
            if decision is None:
                ended = True
                break

            decisions += 1
            if turn % 3 == 2:
                client.post(
                    f"/api/v1/games/{game_id}/actions",
                    json={"input": INPUTS[turn % len(INPUTS)]},
                )
            else:
                options = decision.get("next_choices") or []
                if not options:
                    client.post(
                        f"/api/v1/games/{game_id}/actions", json={"input": "I keep them company"}
                    )
                    continue
                client.post(
                    f"/api/v1/games/{game_id}/choices",
                    json={
                        "step_id": decision["step_id"],
                        "choice_id": options[turn % len(options)]["id"],
                    },
                )

        elapsed = time.monotonic() - started
        state = client.get(f"/api/v1/games/{game_id}").json()
        delivered = len(transcript)

        assert ended, f"the story never ended after {delivered} steps"
        assert delivered > settings.ENDING_MIN_STEPS, (
            f"ended after only {delivered} steps; the gate is {settings.ENDING_MIN_STEPS}"
        )
        assert state["ended"] is True
        assert transcript[-1]["type"] == "ending"
        assert transcript[-1]["narration"], "the ending has no prose"

        # The engine, not the model, wrote the marker.
        assert state["world"]["flags"]["ending"] in ("romance", "friendship", "solo")

        print(
            f"\n  {delivered} steps over {decisions} decisions in {elapsed:.1f}s"
            f"  ->  {state['world']['flags']['ending']} ending"
            f" with {state['world']['flags'].get('ending_partner') or 'nobody'}"
        )

    def test_every_decision_offered_between_three_and_five_options(self, client, transcript):
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]

        counts = []
        for turn in range(60):
            decision = play_until_decision(client, game_id, transcript)
            if decision is None:
                break
            if decision["type"] == "choice":
                counts.append(len(decision["next_choices"]))
            options = decision.get("next_choices") or []
            if options:
                client.post(
                    f"/api/v1/games/{game_id}/choices",
                    json={"step_id": decision["step_id"], "choice_id": options[0]["id"]},
                )
            else:
                client.post(f"/api/v1/games/{game_id}/actions", json={"input": "I wait"})

        assert counts, "no decision points were offered"
        assert min(counts) >= settings.MIN_CHOICES, f"a decision offered only {min(counts)} options"
        assert max(counts) <= settings.MAX_CHOICES, f"a decision offered {max(counts)} options"
        assert len(set(counts)) > 1, "every menu was the same length; 3-5 should vary"

    def test_decisions_come_every_few_clicks_not_every_chapter(self, client, transcript):
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]

        gaps = []
        for _ in range(40):
            before = len(transcript)
            decision = play_until_decision(client, game_id, transcript)
            if decision is None:
                break
            gaps.append(len(transcript) - before)
            options = decision.get("next_choices") or []
            client.post(
                f"/api/v1/games/{game_id}/choices",
                json={"step_id": decision["step_id"], "choice_id": options[0]["id"]},
            )

        assert gaps
        assert max(gaps) <= settings.STEPS_PER_BATCH + 1, (
            f"the player read {max(gaps)} steps before being asked anything"
        )
        assert sum(gaps) / len(gaps) <= settings.STEPS_PER_BATCH

    def test_the_world_moves_across_a_long_save(self, client, transcript):
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]

        arcs, days, times, places = set(), set(), set(), set()
        for turn in range(80):
            decision = play_until_decision(client, game_id, transcript)
            if decision is None:
                break
            world = client.get(f"/api/v1/games/{game_id}").json()["world"]
            arcs.add(world["arc"])
            days.add(world["day"])
            times.add(world["time_of_day"])
            places.add(world["location"])

            options = decision.get("next_choices") or []
            client.post(
                f"/api/v1/games/{game_id}/choices",
                json={"step_id": decision["step_id"], "choice_id": options[turn % len(options)]["id"]},
            )

        assert len(arcs) >= 2, f"the story stayed in one chapter: {arcs}"
        assert len(days) >= 2, "no day ever passed"
        assert len(times) >= 3, f"the clock barely moved: {times}"
        assert len(places) >= 3, f"the story stayed put: {places}"

    def test_a_long_save_stays_a_reasonable_size(self, client, transcript):
        """400 steps is 2.9% of MongoDB's 16MB document limit; this is the guard that
        notices if a step ever grows an unbounded field."""
        import json

        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
        for turn in range(40):
            decision = play_until_decision(client, game_id, transcript)
            if decision is None:
                break
            options = decision.get("next_choices") or []
            client.post(
                f"/api/v1/games/{game_id}/choices",
                json={"step_id": decision["step_id"], "choice_id": options[0]["id"]},
            )

        per_step = len(json.dumps(transcript)) / max(1, len(transcript))
        assert per_step < 4000, f"{per_step:.0f} bytes per step would blow the document limit"


class TestTheEndingReflectsThePlaythrough:
    """The ending has to be *earned*, and it has to be reachable.

    This is the test that caught the relationship system deadlocking: low trust made
    every attempt fail, a failed attempt earned no trust, so a player could spend three
    hundred steps on someone and move nothing but familiarity -- and every playthrough,
    however devoted, ended alone.
    """

    FOCUSED = [
        "I ask Aiko about the council paperwork",
        "I tell Aiko she does not have to carry all of it",
        "I help Aiko with the handouts",
        "I say sorry to Aiko",
        "I tell Aiko I like being around her",
    ]

    def _play(self, client, game_id, inputs, transcript, turns=400):
        for turn in range(turns):
            decision = play_until_decision(client, game_id, transcript)
            if decision is None:
                return True
            client.post(
                f"/api/v1/games/{game_id}/actions", json={"input": inputs[turn % len(inputs)]}
            )
        return False

    def test_devotion_to_one_person_ends_with_them(self, client, transcript):
        game_id = client.post(
            "/api/v1/games", json={"player_name": "Kai", "romance_focus": "aiko"}
        ).json()["game_id"]

        assert self._play(client, game_id, self.FOCUSED, transcript), "the story never ended"
        state = client.get(f"/api/v1/games/{game_id}").json()

        assert state["world"]["flags"]["ending_partner"] == "aiko", (
            "a whole playthrough aimed at one person ended with somebody else"
        )
        assert state["world"]["flags"]["ending"] in ("romance", "friendship")

    def test_a_relationship_actually_moves_over_a_long_save(self, client, transcript):
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
        opening = client.get(f"/api/v1/games/{game_id}").json()["characters"]["aiko"]["relationship"]

        self._play(client, game_id, self.FOCUSED, transcript, turns=60)
        later = client.get(f"/api/v1/games/{game_id}").json()["characters"]["aiko"]["relationship"]

        assert later["trust"] > opening.get("trust", 0) + 10, (
            f"trust barely moved ({opening.get('trust')} -> {later['trust']}); "
            "persistence must be a way past a guarded character"
        )
        assert all(0 <= value <= 100 for value in later.values())

    def test_spreading_yourself_thin_ends_alone(self, client, transcript):
        """Not a bug: a player who never got close to anyone should end on their own."""
        scattered = [
            "I nod at Ren",
            "I wave at Mika",
            "I look at Haruto",
            "I glance at Aiko",
            "I stare out of the window",
        ]
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]

        assert self._play(client, game_id, scattered, transcript)
        assert client.get(f"/api/v1/games/{game_id}").json()["world"]["flags"]["ending"] == "solo"
