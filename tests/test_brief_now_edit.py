"""Adding, replacing, and removing one bullet in `## Now`, in the order the rules give."""

import pytest

from lemonaid.brief import check, now_edit

_BRIEF = """\
# the task

Status: working

Lemon-ID: task.QuickOdd

## Now

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


def test_a_new_heading_goes_in_its_place_with_blank_lines_around_it():
    out = now_edit.add(_BRIEF, "Needs Peter", "merge #12")

    assert _now(out).startswith("\n### Needs Peter\n\n- merge #12\n\n### Waiting on\n")
    assert check.structure(out) == []


def test_running_goes_between_needs_and_waiting_on():
    out = now_edit.add(now_edit.add(_BRIEF, "Needs Peter", "x"), "running", "the backfill, ua:3")

    assert _now(out).index("### Needs Peter") < _now(out).index("### Running")
    assert _now(out).index("### Running") < _now(out).index("### Waiting on")


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


def test_an_out_of_order_now_is_put_in_order():
    brief = _BRIEF.replace("### Waiting on", "### Done\n\n- old\n\n### Waiting on", 1)
    brief = brief.replace("### Done\n\n- parser merged\n", "", 1)

    out = now_edit.add(brief, "Next", "x")

    assert _now(out).index("### Waiting on") < _now(out).index("### Done")
    assert check.structure(out) == []


def test_unknown_headings_and_the_pr_table_have_no_add():
    with pytest.raises(now_edit.EditError, match="not one of"):
        now_edit.add(_BRIEF, "Notes", "x")
    with pytest.raises(now_edit.EditError, match="brief pr add"):
        now_edit.add(_BRIEF, "PRs", "x")


def test_a_brief_without_now_gets_one_under_status():
    out = now_edit.add("# t\n\nStatus: working\n\n## Goal\nx\n", "Next", "start")

    assert out == "# t\n\nStatus: working\n\n## Now\n\n### Next\n\n- start\n\n## Goal\nx\n"
