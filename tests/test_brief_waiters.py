"""Adding, replacing, and removing one waiter's command in `## Waiters`."""

import pytest

from lemonaid.brief import check, waiters

_BRIEF = """\
# the task

Status: waiting

Lemon-ID: task.QuickOdd

## Now

### Waiting on

- #12 review

## Goal
The thing exists.

## Waiters
- `lemonaid inbox watch --self`
- `lemonaid watch pr --wait 5716 --repo o/r --head abc123 --once`
"""


def _waiters(text: str) -> str:
    return text.split("## Waiters\n", 1)[1]


def test_add_appends_a_bullet_in_backticks():
    out = waiters.add(_BRIEF, "lemonaid watch doc --wait /v/r.md --me 'Reviewer (X)'")

    assert _waiters(out).endswith(
        "--once`\n- `lemonaid watch doc --wait /v/r.md --me 'Reviewer (X)'`\n"
    )
    assert check.structure(out) == []


def test_adding_a_listed_command_changes_nothing():
    assert waiters.add(_BRIEF, "lemonaid inbox watch --self") == _BRIEF


def test_a_missing_section_is_added_last():
    without = _BRIEF.split("## Waiters\n", 1)[0]

    out = waiters.add(without, "lemonaid inbox watch --self")

    assert out.endswith("The thing exists.\n\n## Waiters\n- `lemonaid inbox watch --self`\n")
    assert check.structure(out) == []


def test_an_empty_section_takes_its_first_waiter():
    empty = _BRIEF.split("## Waiters\n", 1)[0] + "## Waiters\n"

    assert _waiters(waiters.add(empty, "x --once")) == "- `x --once`\n"


def test_set_with_head_rearms_the_same_waiter():
    out = waiters.replace(_BRIEF, "5716", head="def456")

    assert "- `lemonaid watch pr --wait 5716 --repo o/r --head def456 --once`\n" in out
    assert "abc123" not in out


def test_set_with_head_fills_a_template_placeholder_or_adds_the_flag():
    assert waiters.with_head("watch pr --head <head SHA> --me 'R (X)'", "f00") == (
        "watch pr --head f00 --me 'R (X)'"
    )
    assert waiters.with_head("watch pr --wait 7", "f00") == "watch pr --wait 7 --head f00"


def test_set_replaces_the_whole_command():
    out = waiters.replace(_BRIEF, "inbox", "lemonaid inbox watch --self --quiet")

    assert "- `lemonaid inbox watch --self --quiet`\n- `lemonaid watch pr" in out


def test_rm_removes_the_one_match_and_keeps_notes():
    noted = _BRIEF.replace("## Waiters\n", "## Waiters\n\nArm both once the review is written.\n\n")

    out = waiters.remove(waiters.remove(noted, "inbox watch"), "WATCH PR")

    assert _waiters(out) == "\nArm both once the review is written.\n"
    assert check.structure(out) == []


def test_a_match_must_name_exactly_one_waiter():
    with pytest.raises(waiters.EditError, match="2 waiters contain 'lemonaid'"):
        waiters.remove(_BRIEF, "lemonaid")
    with pytest.raises(waiters.EditError, match="No waiter"):
        waiters.replace(_BRIEF, "watch doc", head="x")


def test_a_note_mentioning_the_match_is_not_a_waiter():
    noted = _BRIEF.replace("## Waiters\n", "## Waiters\nRearm the watch pr waiter on each push.\n")

    assert "--head f00" in waiters.replace(noted, "watch pr", head="f00")


def test_a_command_with_backticks_is_quoted_with_two():
    out = waiters.add(_BRIEF, "sh -c 'echo `date`'")

    assert "- `` sh -c 'echo `date`' ``\n" in out
    assert waiters.remove(out, "echo") == _BRIEF


def test_sections_after_a_misplaced_waiters_stay_put():
    misplaced = _BRIEF.replace("## Goal\nThe thing exists.\n\n", "") + "\n## Goal\nLater.\n"

    out = waiters.remove(misplaced, "inbox")

    assert out.endswith("--once`\n\n## Goal\nLater.\n")


_FENCED = _BRIEF.replace(
    "## Waiters\n",
    "## Waiters\n\n```bash\n# rearm after a push\n- `not a waiter --head zzz`\n```\n\n",
)


def test_a_fenced_note_is_not_the_end_of_the_section():
    out = waiters.add(_FENCED, "lemonaid watch doc --wait /v/r.md")

    assert out.endswith("--once`\n- `lemonaid watch doc --wait /v/r.md`\n")
    assert check.structure(out) == []


def test_a_bullet_in_a_fence_is_not_a_waiter():
    out = waiters.replace(_FENCED, "head", head="f00")

    assert "--head abc123" not in out and "- `not a waiter --head zzz`" in out
    with pytest.raises(waiters.EditError, match="No waiter"):
        waiters.remove(_FENCED, "not a waiter")
    assert waiters.add(_FENCED, "not a waiter --head zzz").endswith("`not a waiter --head zzz`\n")


def test_an_unclosed_fence_refuses_an_add():
    unclosed = _BRIEF.split("## Waiters\n", 1)[0] + "## Waiters\n```\n# a note\n"

    with pytest.raises(waiters.EditError, match="never closed"):
        waiters.add(unclosed, "x --once")


def test_a_waiter_added_after_a_closing_fence_is_outside_it():
    fenced_last = _BRIEF + "\n```\n# rearm after a push\n```\n"

    out = waiters.add(fenced_last, "x --once")

    assert out.endswith("# rearm after a push\n```\n\n- `x --once`\n")
    assert waiters.remove(out, "x --once") == fenced_last


def test_commands_lists_each_waiter_in_order():
    assert waiters.commands(_BRIEF) == [
        "lemonaid inbox watch --self",
        "lemonaid watch pr --wait 5716 --repo o/r --head abc123 --once",
    ]


def test_a_brief_with_no_waiters_section_lists_no_commands():
    assert waiters.commands("# the task\n\nStatus: working\n") == []
