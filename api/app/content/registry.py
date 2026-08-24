"""World lookup. One world in the MVP; the registry is the seam for PRD §32 custom worlds."""

from __future__ import annotations

from app.content.highschool import HIGH_SCHOOL_ROMANCE
from app.content.world import World

WORLDS: dict[str, World] = {HIGH_SCHOOL_ROMANCE.id: HIGH_SCHOOL_ROMANCE}

DEFAULT_WORLD_ID = HIGH_SCHOOL_ROMANCE.id


def get_world(world_id: str | None) -> World:
    if not world_id:
        return WORLDS[DEFAULT_WORLD_ID]
    try:
        return WORLDS[world_id]
    except KeyError as exc:
        raise KeyError(f"unknown world: {world_id}") from exc


def default_world() -> World:
    return WORLDS[DEFAULT_WORLD_ID]
