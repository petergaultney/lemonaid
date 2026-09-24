"""What `brief show` finds in a place and how much of it it shows."""

import os
from pathlib import Path

from lemonaid.brief import status

_BRIEF = """\
# Brief: make the thing

Status: working

## Now
- Done: the parser.
- Next: the popup.

Parent: hq, 2026-09-24.

## Goal
The thing exists.
"""


def _write(notes: Path, name: str, text: str, mtime: float) -> None:
    notes.mkdir(parents=True, exist_ok=True)
    (notes / name).write_text(text)
    os.utime(notes / name, (mtime, mtime))


def test_status_and_now_come_first_and_the_task_goes_below_a_rule(tmp_path):
    _write(tmp_path / ".z", "brief.md", _BRIEF, 1000)

    out = status.render([], [tmp_path], tmp_path, [], now=1000 + 300)

    assert out.startswith("## make the thing")
    assert "Brief:" not in out
    assert str(tmp_path / ".z" / "brief.md") in out
    assert out.index("**Status:** working") < out.index("## Now") < out.index("---")
    assert out.index("- Next: the popup.") < out.index("---") < out.index("## Goal")
    assert "updated 5m ago" in out


def test_parent_stays_with_the_task_even_right_below_now(tmp_path):
    _write(
        tmp_path / ".z", "brief.md", "# x\n\nStatus: working\n\n## Now\n- a\n\nParent: hq\n", 1000
    )

    out = status.render([], [tmp_path], tmp_path, [], now=1000)

    assert out.index("- a") < out.index("---") < out.index("Parent: hq")


def test_a_brief_without_now_shows_status_alone(tmp_path):
    _write(tmp_path / ".z", "brief.md", "# Brief: x\n\nStatus: done - PR #3\n\n## Goal\ny\n", 1000)

    out = status.render([], [tmp_path], tmp_path, [], now=1000)

    assert "**Status:** done" in out
    assert "## Now" not in out


def test_unknown_status_has_no_state(tmp_path):
    _write(tmp_path / ".z", "brief.md", "# x\n\nStatus: reviewing - soon\n", 1000)

    out = status.render([], [tmp_path], tmp_path, [], now=1000)

    assert "**Status:** reviewing - soon" in out
    assert "- Note: soon" not in out


def test_the_brief_named_for_the_session_wins(tmp_path):
    _write(tmp_path / ".z", "brief-pliny.md", "# A\n\nStatus: working\n", 1000)
    _write(tmp_path / ".z", "brief-quokka.md", "# B\n\nStatus: blocked - need a key\n", 2000)

    out = status.render([], [tmp_path], tmp_path, ["nosuch", "Pliny"], now=2000)

    assert out.startswith("## A")
    assert "## B" not in out


def test_several_unmatched_briefs_are_listed_newest_first_without_their_tasks(tmp_path):
    _write(tmp_path / ".z", "brief-pliny.md", _BRIEF.replace("make the thing", "older"), 1000)
    _write(tmp_path / ".z", "brief-quokka.md", _BRIEF.replace("make the thing", "newer"), 2000)

    out = status.render([], [tmp_path], tmp_path, ["someone-else"], now=2000)

    assert out.index("## newer") < out.index("## older")
    assert "Brief:" not in out
    assert "## Goal" not in out


def test_state_md_stands_in_for_a_missing_brief(tmp_path):
    _write(tmp_path / ".z", "state.md", "Halfway through the migration.\n", 1000)

    out = status.render([], [tmp_path], tmp_path, [], now=1000 + 7200)

    assert out.startswith("## Work status")
    assert "Halfway through the migration." in out
    assert "updated 2h ago" in out


def test_nothing_at_all_says_so(tmp_path):
    assert status.render([], [tmp_path], tmp_path, [], now=0).startswith("## Work status")


def test_notes_are_found_above_a_subdirectory(tmp_path):
    (tmp_path / ".z").mkdir()
    (tmp_path / "src" / "pkg").mkdir(parents=True)

    assert status.notes_dir(tmp_path / "src" / "pkg", tmp_path) == tmp_path / ".z"


def test_a_brief_above_the_place_is_not_the_places(tmp_path):
    place = tmp_path / "support-katamari"
    (place / "protostellar" / "visits").mkdir(parents=True)
    _write(tmp_path / ".z", "brief.md", "# someone else's\n\nStatus: working\n", 1000)

    out = status.render([], [place / "protostellar" / "visits", place], place, [], now=1000)

    assert "someone else's" not in out
    assert out.startswith("## Work status\n\nNothing in")


def test_without_a_place_only_each_directorys_own_notes_are_read(tmp_path):
    (tmp_path / ".z").mkdir()
    (tmp_path / "src").mkdir()

    assert status.notes_dir(tmp_path / "src", None) == tmp_path / "src" / ".z"


def test_a_directory_outside_the_place_is_not_searched(tmp_path):
    (tmp_path / ".z").mkdir()
    (tmp_path / "elsewhere" / ".z").mkdir(parents=True)
    (tmp_path / "place").mkdir()

    assert status.notes_dir(tmp_path / "elsewhere", tmp_path / "place") is None


def test_a_lemon_cwd_outside_the_place_has_no_brief(tmp_path):
    session_dir, lemon_cwd = tmp_path / "session", tmp_path / "lemon"
    session_dir.mkdir()
    _write(lemon_cwd / ".z", "brief.md", "# lemon's\n\nStatus: working\n", 1000)

    out = status.render([], [lemon_cwd, session_dir], session_dir, [], now=1000)

    assert "lemon's" not in out
    assert out.startswith("## Work status\n\nNothing in")


def test_the_first_directory_with_a_brief_wins(tmp_path):
    session_dir = tmp_path / "session"
    lemon_cwd = session_dir / "lemon"
    _write(session_dir / ".z", "brief.md", "# session's\n\nStatus: working\n", 1000)
    _write(lemon_cwd / ".z", "brief.md", "# lemon's\n\nStatus: working\n", 1000)

    assert status.render([], [lemon_cwd, session_dir], session_dir, [], now=1000).startswith(
        "## lemon's"
    )


def test_a_brief_in_a_later_directory_beats_state_in_an_earlier_one(tmp_path):
    session_dir = tmp_path / "session"
    lemon_cwd = session_dir / "lemon"
    _write(lemon_cwd / ".z", "state.md", "halfway\n", 1000)
    _write(session_dir / ".z", "brief.md", "# the task\n\nStatus: working\n", 1000)

    assert status.render([], [lemon_cwd, session_dir], session_dir, [], now=1000).startswith(
        "## the task"
    )
