"""Adding, replacing, and removing one bullet in `## Now`, in the order the rules give."""

import pytest

from lemonaid.brief import check, doc_table, migrate, now_edit, pr_table, sections

_BRIEF = """\
# the task

Status: working

Lemon-ID: task.QuickOdd

## Now

### Needs you

- merge #12

### Waiting on

- #12 review: reviewer reading it

### Next

- write the docs
- tag the release

### Done

- parser merged

## Questions

### merge #12

- **Context:** untouched by the verbs

Parent: hq, 2026-09-30

## Goal
The thing exists.

## Waiters
- lemonaid inbox watch --self
"""


def _now(text: str) -> str:
    return text.split("## Now\n", 1)[1].split("\n## ", 1)[0]


def test_a_new_heading_keeps_existing_headings_in_place():
    out = now_edit.add(
        _BRIEF.replace("### Needs you\n\n- merge #12\n\n", ""), "Needs you", "merge #12"
    )

    assert "### Needs you\n\n- merge #12\n" in out
    assert _now(out).index("### Waiting on") < _now(out).index("### Needs you")
    assert check.structure(out) == []


def test_running_is_added_without_reordering():
    out = now_edit.add(now_edit.add(_BRIEF, "Needs you", "x"), "running", "the backfill, ua:3")

    assert _now(out).index("### Needs you") < _now(out).index("### running")
    assert _now(out).index("### Waiting on") < _now(out).index("### running")


def test_add_appends_to_a_heading_but_done_adds_at_the_top():
    out = now_edit.add(now_edit.add(_BRIEF, "Next", "open the PR"), "Done", "docs written")

    assert "- tag the release\n- open the PR\n" in out
    assert "### Done\n\n- docs written\n- parser merged\n" in out


def test_everything_outside_now_is_left_as_written():
    out = now_edit.remove(now_edit.add(_BRIEF, "Next", "x"), "x")

    assert out.split("## Questions", 1)[1] == _BRIEF.split("## Questions", 1)[1]
    assert out.split("## Now", 1)[0] == _BRIEF.split("## Now", 1)[0]


def test_set_replaces_the_one_bullet_its_lead_names():
    out = now_edit.replace(_BRIEF, "#12 review", "#12 review: changes requested")

    assert "- #12 review: changes requested\n" in out
    assert "reviewer reading it" not in out


def test_a_lead_matching_several_bullets_or_none_is_refused():
    with pytest.raises(now_edit.EditError, match="2 bullets"):
        now_edit.replace(now_edit.add(_BRIEF, "Next", "write the tests"), "write", "x")
    with pytest.raises(now_edit.EditError, match="No bullet"):
        now_edit.remove(_BRIEF, "nothing like this")


def test_removing_a_headings_last_bullet_removes_the_heading():
    out = now_edit.remove(_BRIEF, "parser merged")

    assert "### Done" not in out
    assert check.structure(out) == []


def test_a_bullet_keeps_the_lines_under_it():
    brief = _BRIEF.replace("- write the docs\n", "- write the docs\n  - for-lemons.md\n")

    out = now_edit.replace(brief, "tag", "publish")
    removed = now_edit.remove(brief, "write")

    assert "- write the docs\n  - for-lemons.md\n- publish\n" in out
    assert "for-lemons.md" not in removed


def test_a_parent_line_inside_now_stays_at_its_end():
    brief = _BRIEF.replace("## Questions", "Parent: hq, 2026-09-29\n\n## Questions", 1)

    out = now_edit.add(brief, "Next", "x")

    assert "- parser merged\n\nParent: hq, 2026-09-29\n\n## Questions" in out


def test_existing_now_order_is_preserved():
    brief = _BRIEF.replace("### Waiting on", "### Done\n\n- old\n\n### Waiting on", 1)
    brief = brief.replace("### Done\n\n- parser merged\n", "", 1)

    out = now_edit.add(brief, "Next", "x")

    assert _now(out).index("### Done") < _now(out).index("### Waiting on")
    assert check.structure(out) == []


def test_unknown_headings_can_be_created():
    out = now_edit.add(_BRIEF, "Notes", "x")
    assert "## Notes\n\n- x" in out


def test_a_new_promoted_heading_is_level_two_without_creating_now():
    out = now_edit.add("# t\n\n## Goal\nx\n", "Next", "start")
    assert "## Next\n\n- start" in out
    assert "## Now" not in out


def test_replacing_progress_leaves_promoted_tables_untouched(tmp_path):
    brief = now_edit.with_section(
        _BRIEF,
        "PRs",
        lambda body: pr_table.with_row(body, "https://github.com/o/r/pull/12", "Fix", None),
    )
    brief = doc_table.add(brief, tmp_path / "review.md", "Review")
    brief = migrate.layout(brief)
    out = now_edit.replace_progress(brief, "Code finished.\n", replace_all=True)

    assert "write the docs" in out
    assert sections.body(out, sections.find(out, "PRs")) == sections.body(
        brief, sections.find(brief, "PRs")
    )
    assert sections.body(out, sections.find(out, "Docs")) == sections.body(
        brief, sections.find(brief, "Docs")
    )


def test_replacing_progress_can_explicitly_replace_or_clear_a_table():
    brief = now_edit.with_section(
        "# task\n\n## Now\n\n### PRs\n",
        "PRs",
        lambda body: pr_table.with_row(body, "https://github.com/o/r/pull/12", "Old", None),
    )
    table = "\n".join(pr_table.with_row([], "https://github.com/o/r/pull/13", "New", None))
    out = now_edit.replace_progress(brief, f"### PRs\n\n{table}\n")
    assert "pull/12" not in out and "pull/13" in out
    assert "### PRs" not in now_edit.replace_progress(out, "### PRs\n")
    removed = now_edit.with_section(out, "PRs", lambda body: pr_table.without(body, "13"))
    assert "### PRs" not in removed


def test_replacing_progress_refuses_to_drop_a_sub_heading():
    with pytest.raises(now_edit.EditError, match="### Next") as refused:
        now_edit.replace_progress(_BRIEF, "### Done\n\n- Code finished\n")

    assert "- merge #12" in str(refused.value) and "write the docs" in str(refused.value)


def test_replacing_progress_keeping_every_sub_heading_needs_no_flag():
    kept = "### Needs you\n\n- x\n\n### Waiting on\n\n- y\n\n### Next\n\n- something else\n\n### Done\n\n- z\n"
    out = now_edit.replace_progress(_BRIEF, kept)

    assert "something else" in out and "write the docs" not in out


def test_replacing_progress_refuses_an_empty_heading_that_would_vanish():
    with pytest.raises(now_edit.EditError, match="### Waiting on"):
        now_edit.replace_progress(_BRIEF, "### Waiting on\n")


def test_replacing_progress_requires_each_persons_needs_heading():
    brief = "# task\n\n## Now\n\n### Needs Sam\n\n- decide\n\n### Needs Ben\n\n- review\n"
    with pytest.raises(now_edit.EditError, match="drop ### Needs Ben"):
        now_edit.replace_progress(brief, "### Needs Sam\n\n- changed")

    out = now_edit.replace_progress(brief, "### Needs Sam\n\n- changed", replace_all=True)
    assert "### Needs Ben" not in out
    assert "### Needs Sam\n\n- changed" in out
