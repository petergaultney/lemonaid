"""The prompt a restored lemon starts with."""

from pathlib import Path

from lemonaid.restore import prompt

_BRIEF = Path("/briefs/task.md")
_TEXT = """\
# the task

Status: waiting

## Waiters
- `lemonaid inbox watch --self`
- `lemonaid watch doc --wait /vault/design.md --me 'Author (QuickOdd)' --once`
"""


def test_a_claude_lemon_rearms_every_waiter_its_brief_lists():
    text = prompt.rearm(_BRIEF, _TEXT, "claude")

    assert str(_BRIEF) in text
    assert "- `lemonaid inbox watch --self`" in text
    assert "- `lemonaid watch doc --wait /vault/design.md" in text


def test_a_codex_lemon_has_no_inbox_waiter_to_rearm():
    text = prompt.rearm(_BRIEF, _TEXT, "codex")

    assert "inbox watch" not in text
    assert "lemonaid watch doc" in text


def test_a_brief_that_lists_nothing_gets_no_prompt():
    assert prompt.rearm(_BRIEF, "# the task\n\n## Waiters\n", "claude") == ""


def test_a_codex_brief_with_only_an_inbox_waiter_gets_no_prompt():
    only_inbox = "# the task\n\n## Waiters\n- `lemonaid inbox watch --self`\n"

    assert prompt.rearm(_BRIEF, only_inbox, "codex") == ""
