"""Brief files: where they go, and the two edits a worker makes to one."""

import datetime

import pytest

from lemonaid.brief import store

_BRIEF = """\
# the task

Status: working

## Now
- Starting.

Parent: hq, 2026-09-24.

## Goal
The thing exists.

## Waiters
- watch-pr #66
"""


def test_status_replaces_the_first_status_line_only():
    out = store.with_status(_BRIEF + "\nStatus: in a code block\n", "done")

    assert "Status: done\n" in out
    assert "## Now\n- Starting." in out
    assert "Status: working" not in out
    assert "Status: in a code block" in out


def test_status_is_the_bare_state():
    assert "\nStatus: blocked\n" in store.with_status(_BRIEF, "blocked")


def test_status_leaves_now_alone():
    brief = _BRIEF.replace("- Starting.", "- Note: old\n- Starting.")

    updated = store.with_status(brief, "waiting")

    assert "Status: waiting\n" in updated
    assert "## Now\n- Note: old\n- Starting." in updated


def test_status_goes_under_the_title_when_missing():
    assert store.with_status("# t\n\n## Goal\nx\n", "working") == (
        "# t\n\nStatus: working\n\n## Goal\nx\n"
    )


def test_now_replaces_only_its_section():
    out = store.with_now(_BRIEF, "- Done: parser.\n- Next: popup.")

    assert "- Starting." not in out
    assert out.index("## Now\n- Done: parser.\n- Next: popup.\n\n") < out.index("## Goal")
    assert out.endswith("## Waiters\n- watch-pr #66\n")


def test_now_is_added_after_status_when_missing():
    out = store.with_now("# t\n\nStatus: working\n\n## Goal\nx\n", "- a")

    assert out.index("Status: working") < out.index("## Now\n- a") < out.index("## Goal")


def test_new_briefs_are_dated_and_named_after_the_work():
    path = store.create("Lemonaid: session briefs!", datetime.date(2026, 9, 24))

    assert path.name == "2026-09-24-lemonaid-session-briefs.md"
    assert path.parent == store.briefs_dir().resolve()
    assert path.read_text().startswith("# Lemonaid: session briefs!\n\nStatus: working\n")


def test_new_never_overwrites():
    store.create("same", datetime.date(2026, 9, 24))

    with pytest.raises(FileExistsError):
        store.create("same", datetime.date(2026, 9, 24))


def test_relative_names_are_inside_the_briefs_dir(tmp_path):
    assert store.resolve("2026-09-24-x") == (store.briefs_dir() / "2026-09-24-x.md").resolve()
    assert store.resolve(str(tmp_path / "elsewhere.md")) == (tmp_path / "elsewhere.md").resolve()


def test_a_concurrent_save_survives_the_edit(tmp_path):
    path = tmp_path / "brief.md"
    path.write_text(_BRIEF)
    calls = []

    def change(text: str) -> str:
        calls.append(text)
        if len(calls) == 1:
            path.write_text(text.replace("The thing exists.", "Edited in Obsidian."))
        return store.with_status(text, "done")

    store.edit(path, change)

    assert len(calls) == 2
    assert "Edited in Obsidian." in path.read_text()
    assert "Status: done" in path.read_text()


def test_an_edit_keeps_the_mode_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "brief.md"
    path.write_text(_BRIEF)
    path.chmod(0o640)

    store.edit(path, lambda text: store.with_now(text, "- x"))

    assert oct(path.stat().st_mode & 0o777) == "0o640"
    assert [p.name for p in tmp_path.iterdir()] == ["brief.md"]


def test_a_file_that_never_settles_is_refused(tmp_path):
    path = tmp_path / "brief.md"
    path.write_text(_BRIEF)
    count = iter(range(100))

    def change(text: str) -> str:
        path.write_text(f"{_BRIEF}{next(count)}")
        return text

    with pytest.raises(store.ChangedUnderneath):
        store.edit(path, change)
