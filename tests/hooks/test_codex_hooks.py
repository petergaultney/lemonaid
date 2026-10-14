"""Codex's Stop and SessionStart hooks: the Claude checks, minus the inbox waiter Codex doesn't need."""

import json

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.claude import waiter_check
from lemonaid.hooks import session_start
from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.watch import children_waiter

_THREAD = "019a0000-1111-2222-3333-444444444444"


def _briefed(name: str = "lemon", channel: str = f"codex:{_THREAD}", body: str = "") -> str:
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: working\n{body}")
    with db.connect() as conn:
        db.add(conn, channel, "", metadata={})
        attached.attach(conn, channel, path)
        return identity.ensure(conn, path)


def _stop(capsys) -> dict | None:
    waiter_check.handle(json.dumps({"session_id": _THREAD}), grace=0.0, harness="codex")
    out = capsys.readouterr().out
    return json.loads(out) if out else None


def test_a_codex_lemon_needs_no_inbox_waiter(capsys):
    _briefed()

    assert _stop(capsys) is None


def test_a_codex_parent_without_a_children_waiter_is_blocked_with_the_codex_command(capsys):
    parent = _briefed()
    child = brief_store.briefs_dir() / "child.md"
    child.write_text("# child\n\nStatus: working\n")
    with db.connect() as conn:
        links.set_parent(conn, identity.ensure(conn, child), parent)

    blocked = _stop(capsys)

    assert blocked is not None
    assert blocked["decision"] == "block"
    assert children_waiter.CODEX_REMINDER in blocked["reason"]


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_session_start_lists_the_briefs_waiters(harness):
    session = _THREAD if harness == "codex" else "abcd1234-0000"
    _briefed(
        channel=f"codex:{_THREAD}" if harness == "codex" else "claude:abcd1234",
        body="\n## Waiters\n\n- `lemonaid watch pr --wait 12 --once`\n",
    )

    text = session_start.context({"session_id": session}, harness)

    assert "- `lemonaid watch pr --wait 12 --once`" in text
    assert ("inbox watch --self" in text) is (harness == "claude")


def test_session_start_says_nothing_without_a_brief():
    assert session_start.context({"session_id": _THREAD}, "codex") == ""
