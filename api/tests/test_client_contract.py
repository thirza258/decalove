"""Does the Ren'Py client agree with the API it talks to?

Without the SDK the client cannot be run, so the failure mode to defend against
is drift: a route the client calls that does not exist, or a JSON field it reads
that the server never sends. Both would look fine in every other test here and
crash on the first real playthrough.

So: pull the endpoints straight out of the .rpy source, call them for real, and
assert every field the client dereferences is present.
"""

from __future__ import annotations

import re
from pathlib import Path

CLIENT = Path(__file__).resolve().parent.parent.parent / "game" / "decalove"

#: Endpoints as written in the client, with their %s slots named.
API_CALL = re.compile(r"""decalove_api\.(get|post)\(\s*\n?\s*["']([^"']+)["']""")


def client_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(CLIENT.glob("*.rpy")))


def declared_endpoints() -> set[tuple[str, str]]:
    return {(verb.upper(), path) for verb, path in API_CALL.findall(client_source())}


def test_the_client_calls_only_routes_that_exist(client):
    """Every URL literal in the client resolves, with the %s slots filled in."""
    game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]

    endpoints = declared_endpoints()
    assert endpoints, "no API calls found in the client source"

    for verb, template in sorted(endpoints):
        path = "/api/v1" + (template % game_id if "%s" in template else template)
        if verb == "GET":
            response = client.get(path)
        else:
            body = {
                "/games": {"player_name": "Kai"},
                "/games/%s/actions": {"input": "I wave at Aiko."},
                "/games/%s/choices": {"step_id": "step_00000", "choice_id": "choice_1"},
            }.get(template, {})
            response = client.post(path, json=body)

        assert response.status_code != 404, f"client calls {verb} {path}, which does not exist"
        assert response.status_code < 500, f"{verb} {path} -> {response.status_code}"


def test_world_payload_has_every_field_the_client_reads(client):
    world = client.get("/api/v1/worlds").json()

    assert "title" in world  # decalove_world_title
    for character in world["characters"]:
        assert {"id", "name", "palette"} <= set(character), "sprite placeholders need these"
        assert len(character["palette"]) >= 2, "decalove_gradient needs two stops"
    for location in world["locations"]:
        assert {"id", "name", "palette", "ambience"} <= set(location)
        assert len(location["palette"]) >= 2


def test_step_payload_has_every_field_the_client_reads(client):
    game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]

    seen_dialogue = False
    seen_choice = False
    for _ in range(20):
        body = client.get(f"/api/v1/games/{game_id}/steps/next", params={"wait_ms": 2000}).json()

        assert "status" in body
        if body["status"] == "pending":
            assert isinstance(body.get("ambience"), list)
            continue
        if body["status"] in ("awaiting_player", "ready"):
            step = body["step"]
            # Read by decalove_render / decalove_speak / decalove_decide.
            for field in (
                "step_id",
                "type",
                "location",
                "narration",
                "dialogue",
                "next_choices",
                "visual",
                "background_asset",
                "character_asset",
            ):
                assert field in step, f"client reads step[{field!r}], server does not send it"

            assert "background" in step["visual"]
            assert "character" in step["visual"]
            assert "expression" in step["visual"]

            if step["dialogue"]:
                assert {"speaker", "text"} <= set(step["dialogue"])
                seen_dialogue = True
            for choice in step["next_choices"]:
                assert {"id", "text"} <= set(choice)
            if step["type"] in ("choice", "prompt"):
                seen_choice = True
                break
        if body["status"] == "ended":
            break

    assert seen_dialogue, "the opening should have produced at least one line of dialogue"
    assert seen_choice, "the opening should have ended at a decision point"


def test_asset_refs_carry_what_the_image_loader_needs(client):
    """decalove_remote_image reads status/url/asset_id/cache_key off an AssetRef."""
    game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
    body = client.get(f"/api/v1/games/{game_id}/steps/next", params={"wait_ms": 2000}).json()
    ref = body["step"]["background_asset"]

    assert ref is not None
    assert {"status", "url", "asset_id", "cache_key"} <= set(ref)
    # Image generation is off by default, so the client must fall back to placeholders.
    assert ref["status"] in ("ready", "pending", "unavailable")


def test_accepted_responses_are_202_not_200(client):
    """The client treats a non-None body as 'submitted'; the contract is 202 + batch id."""
    game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
    response = client.post(f"/api/v1/games/{game_id}/actions", json={"input": "I look around."})

    assert response.status_code == 202
    assert response.json()["batch_id"]
