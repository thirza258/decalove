"""Static checks on the Ren'Py client.

The Ren'Py SDK is not a Python package, so the game cannot be launched from this
test suite. What *can* be checked without it is the class of mistake that is both
most likely and most expensive here: a syntax or indentation error inside a
``python:`` block, a ``call`` to a label that does not exist, or a screen invoked
by a name nothing defines. All three are silent until the engine loads the file.

This does not replace a playtest -- see docs/ARCHITECTURE.md for what is still
deferred until the SDK is available.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parent.parent.parent / "game"

PYTHON_HEADER = re.compile(r"^(init(\s+-?\d+)?\s+)?python(\s+(hide|early|in\s+\w+))*\s*:\s*$")
INLINE_PYTHON = re.compile(r"^\$\s+(.*)$")
LABEL_DEF = re.compile(r"^label\s+([\w.]+)\s*(\(.*\))?\s*:")
SCREEN_DEF = re.compile(r"^screen\s+(\w+)\s*(\(.*\))?\s*:")
CALL_LABEL = re.compile(r"^(call|jump)\s+(?!screen\b|expression\b)([\w.]+)")
CALL_SCREEN = re.compile(r"^(call|show)\s+screen\s+(\w+)")
SCREEN_IN_PYTHON = re.compile(r"""renpy\.(?:call_screen|show_screen)\(\s*["'](\w+)["']""")
TRANSFORM_DEF = re.compile(r"^transform\s+(\w+)\s*(\(.*\))?\s*:")


def rpy_files() -> list[Path]:
    return sorted(p for p in GAME.rglob("*.rpy") if "tl/" not in str(p))


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def python_blocks(path: Path):
    """Yield ``(first_line_number, source)`` for every ``python:`` block."""
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip() and PYTHON_HEADER.match(line.strip()):
            header_indent = indent_of(line)
            body: list[str] = []
            cursor = index + 1
            while cursor < len(lines):
                candidate = lines[cursor]
                if candidate.strip() and indent_of(candidate) <= header_indent:
                    break
                body.append(candidate)
                cursor += 1
            if any(entry.strip() for entry in body):
                yield index + 2, textwrap.dedent("\n".join(body))
            index = cursor
            continue
        index += 1


def test_the_client_files_are_where_the_loader_expects_them():
    assert GAME.is_dir(), f"no game directory at {GAME}"
    names = {p.name for p in (GAME / "decalove").glob("*.rpy")}
    assert names, "the Decalove client files are missing"
    assert "50_player.rpy" in names


@pytest.mark.parametrize("path", rpy_files(), ids=lambda p: p.name)
def test_python_blocks_compile(path: Path):
    for line_number, source in python_blocks(path):
        try:
            compile(source, f"{path.name}:{line_number}", "exec")
        except SyntaxError as exc:
            pytest.fail(
                f"{path.relative_to(GAME)} python block at line {line_number}: "
                f"{exc.msg} (block line {exc.lineno})"
            )


@pytest.mark.parametrize("path", rpy_files(), ids=lambda p: p.name)
def test_inline_python_statements_compile(path: Path):
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = INLINE_PYTHON.match(line.strip())
        if not match:
            continue
        try:
            compile(match.group(1), f"{path.name}:{number}", "exec")
        except SyntaxError as exc:
            pytest.fail(f"{path.relative_to(GAME)}:{number} `$` statement: {exc.msg}")


def collect(pattern: re.Pattern, group: int = 1) -> set[str]:
    found: set[str] = set()
    for path in rpy_files():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line.strip())
            if match:
                found.add(match.group(group).strip())
    return found


def test_every_called_label_exists():
    defined = collect(LABEL_DEF) | {"start", "quit", "after_load", "main_menu", "splashscreen"}
    called = collect(CALL_LABEL, group=2)
    missing = called - defined
    assert missing == set(), f"call/jump to undefined label(s): {sorted(missing)}"


def test_every_invoked_screen_exists():
    defined = collect(SCREEN_DEF)
    invoked = collect(CALL_SCREEN, group=2)
    for path in rpy_files():
        invoked |= set(SCREEN_IN_PYTHON.findall(path.read_text(encoding="utf-8")))
    missing = invoked - defined
    assert missing == set(), f"screen(s) invoked but never defined: {sorted(missing)}"


def test_at_list_transforms_are_defined():
    transforms = collect(TRANSFORM_DEF)
    player = (GAME / "decalove" / "50_player.rpy").read_text(encoding="utf-8")
    for name in re.findall(r"at_list=\[(\w+)\]", player):
        assert name in transforms, f"at_list references undefined transform {name!r}"


def test_rollback_is_disabled():
    """The server cursor only moves forward; rollback would desync the story."""
    config = (GAME / "decalove" / "00_config.rpy").read_text(encoding="utf-8")
    assert "config.rollback_enabled = False" in config


def test_fetch_timeouts_exceed_the_long_poll_window():
    """renpy.fetch defaults to 5s. A long poll that outlives its own timeout would
    surface a successful response as a FetchError."""
    config = (GAME / "decalove" / "00_config.rpy").read_text(encoding="utf-8")
    api = (GAME / "decalove" / "10_api.rpy").read_text(encoding="utf-8")

    wait_ms = int(re.search(r"DECALOVE_WAIT_MS\s*=\s*(\d+)", config).group(1))
    margin = float(re.search(r"DECALOVE_HTTP_MARGIN\s*=\s*([\d.]+)", config).group(1))

    assert "timeout = (wait_ms / 1000.0) + DECALOVE_HTTP_MARGIN" in api
    assert margin >= 2.0, "too little headroom over the server's own hold time"
    assert wait_ms / 1000.0 < wait_ms / 1000.0 + margin


def test_control_flow_exceptions_are_not_swallowed():
    """A bare `except Exception` around renpy.fetch would eat the player's quit."""
    api = (GAME / "decalove" / "10_api.rpy").read_text(encoding="utf-8")
    assert "_decalove_is_control_flow" in api
    assert api.count("if _decalove_is_control_flow(exc):") >= 2


def strip_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))


def test_free_text_input_is_not_opened_from_inside_a_screen():
    """renpy.input starts an interaction, and a screen already is one."""
    screens = (GAME / "decalove" / "40_screens.rpy").read_text(encoding="utf-8")
    assert "renpy.input" not in strip_comments(screens), (
        "the choice screen must return a sentinel, not open the input itself"
    )
    assert '"__freetext__"' in screens
    assert "renpy.input(" in (GAME / "decalove" / "50_player.rpy").read_text(encoding="utf-8")


def test_ambient_filler_is_capped():
    """Three lines per location on a 20s generation reads as a hang if repeated."""
    player = (GAME / "decalove" / "50_player.rpy").read_text(encoding="utf-8")
    state = (GAME / "decalove" / "30_state.rpy").read_text(encoding="utf-8")
    assert "DECALOVE_AMBIENT_LIMIT" in player
    assert "ambient_index + 1) % len(ambience)" in state, "filler must not repeat back to back"


def test_saves_store_only_the_game_id():
    """The step ledger lives on the server; copying it into a save invites divergence."""
    state = (GAME / "decalove" / "30_state.rpy").read_text(encoding="utf-8")
    assert "default decalove_game_id = None" in state
    assert "label after_load:" in state
