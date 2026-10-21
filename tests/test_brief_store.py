"""Brief files: where they go, and the two edits a worker makes to one."""

import datetime
import os

import pytest

from lemonaid.brief import frontmatter, store
from lemonaid.config import get_config_path

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


def test_status_ignores_status_lines_below_the_header():
    brief = "# t\n\n## Goal\n```\nStatus: quoted\n```\n"

    assert store.with_status(brief, "blocked") == (
        "# t\n\nStatus: blocked\n\n## Goal\n```\nStatus: quoted\n```\n"
    )
    assert store.with_status(brief, "clear") == brief


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


def test_now_is_added_before_the_first_section_without_a_status():
    out = store.with_now("# t\n\nParent: hq\n\n## Goal\nx\n", "- a")

    assert out == "# t\n\nParent: hq\n\n## Now\n- a\n\n## Goal\nx\n"


def test_clear_removes_the_status_line_and_its_blank_line():
    text = "# t\n\nStatus: blocked\n\nParent: hq\n\n## Now\n- a\n"

    assert store.with_status(text, store.CLEAR) == "# t\n\nParent: hq\n\n## Now\n- a\n"
    assert store.with_status("# t\n\n## Now\n- a\n", store.CLEAR) == "# t\n\n## Now\n- a\n"


def test_new_briefs_are_dated_and_named_after_the_work():
    path = store.create("Lemonaid: session briefs!", datetime.date(2026, 9, 24))
    text = path.read_text()

    assert path.name == "2026-09-24-lemonaid-session-briefs.md"
    assert path.parent == store.briefs_dir().resolve()
    assert text.startswith("---\ntype: Brief\ncreated: { at: 2026-09-24 }\n")
    assert frontmatter.fields(text)["brief-id"].endswith(".lemonaid-session-briefs")
    assert "\n---\n# Lemonaid: session briefs!\n\n## Now\n" in text
    assert "status" not in frontmatter.fields(text)
    assert [line for line in text.splitlines() if line.startswith("## ")] == [
        "## Now",
        "## Questions",
        "## Next",
        "## PRs",
        "## Docs",
        "## Done",
        "## Goal",
        "## Executive Summary of Results",
        "## Context",
        "## Acceptance Criteria",
        "## Limits",
        "## Watching",
    ]


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
    assert frontmatter.fields(path.read_text())["status"] == "done"


def test_an_edit_keeps_the_mode_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "brief.md"
    path.write_text(_BRIEF)
    path.chmod(0o640)

    store.edit(path, lambda text: store.with_now(text, "- x"))

    assert oct(path.stat().st_mode & 0o777) == "0o640"
    assert [p.name for p in tmp_path.iterdir() if p.name != "state"] == ["brief.md"]


def test_a_file_that_never_settles_is_refused(tmp_path):
    path = tmp_path / "brief.md"
    path.write_text(_BRIEF)
    count = iter(range(100))

    def change(text: str) -> str:
        path.write_text(f"{_BRIEF}{next(count)}")
        return f"{text}edited\n"

    with pytest.raises(store.ChangedUnderneath):
        store.edit(path, change)


def test_an_edit_that_changes_nothing_leaves_the_file_alone(tmp_path):
    path = tmp_path / "brief.md"
    path.write_text(_BRIEF)
    os.utime(path, (1000, 1000))

    store.edit(path, lambda text: text)

    assert path.stat().st_mtime == 1000


def test_new_briefs_keep_created_lines_through_status_and_now_edits():
    stamp = "created: { at: 2026-10-21T08:15:00-04:00, by: LemonAce }"
    path = store.create("Stamped", datetime.date(2026, 10, 21), created=lambda _: stamp)

    assert stamp in frontmatter.split(path.read_text())[0]
    assert frontmatter.fields(path.read_text())["contributors"] == ["LemonAce"]
    for change in (
        lambda text: store.with_status(text, "blocked"),
        lambda text: store.with_status(text, store.CLEAR),
        lambda text: store.with_now(text, "- Working."),
    ):
        store.edit(path, change)
        assert stamp in frontmatter.split(path.read_text())[0]


def test_the_first_write_to_a_legacy_brief_gives_it_frontmatter(tmp_path):
    path = tmp_path / "2026-10-02-task.md"
    path.write_text("# task\n\nBrief-ID: task.SkullHen\n\nStatus: working\n\n## Now\n- Starting.\n")

    store.edit(path, lambda text: store.with_status(text, "blocked"))

    found = frontmatter.fields(path.read_text())
    assert (found["type"], found["brief-id"], found["status"]) == (
        "Brief",
        "task.SkullHen",
        "blocked",
    )
    assert found["created"] == {"at": datetime.date(2026, 10, 2)}
    assert frontmatter.split(path.read_text())[1] == "# task\n\n## Now\n- Starting.\n"


def test_an_edit_that_changes_nothing_leaves_a_legacy_brief_legacy(tmp_path):
    path = tmp_path / "brief.md"
    path.write_text(_BRIEF)

    store.edit(path, lambda text: text)
    assert path.read_text() == _BRIEF

    store.edit(path, lambda text: text, convert=True)
    assert frontmatter.has_block(path.read_text())


def test_backfilling_an_id_does_not_convert_the_brief(tmp_path):
    path = tmp_path / "brief.md"
    path.write_text("# task\n\nStatus: working\n")

    store.edit(
        path,
        lambda text: text.replace("# task\n", "# task\n\nBrief-ID: t.SkullHen\n"),
        migrate=False,
    )

    assert path.read_text().startswith("# task\n\nBrief-ID: t.SkullHen\n")


def test_an_editor_is_added_to_contributors(tmp_path):
    path = store.create(
        "Edited",
        datetime.date(2026, 10, 21),
        created=lambda _: "created: { at: 2026-10-21, by: BlessBar }",
    )

    store.edit(path, lambda text: store.with_status(text, "done"), "PriceHum")

    assert frontmatter.fields(path.read_text())["contributors"] == ["BlessBar", "PriceHum"]


def test_a_new_brief_names_the_configured_responsible_parties():
    get_config_path().write_text('[brief]\nresponsible_parties = ["Sam Smith", "Pat Lee"]\n')

    path = store.create("Owned", datetime.date(2026, 10, 21))

    assert frontmatter.fields(path.read_text())["responsible-parties"] == ["Sam Smith", "Pat Lee"]
