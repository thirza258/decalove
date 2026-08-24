"""Authored world content. The MVP ships one world — PRD §29."""

from app.content.registry import WORLDS, default_world, get_world

__all__ = ["WORLDS", "get_world", "default_world"]
