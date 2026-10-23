"""Codex's Stop and SessionStart hooks: the Claude checks, minus the inbox waiter Codex doesn't need."""

import json

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.hooks import session_start, stop_check
from lemonaid.inbox import db
from lemonaid.lineage import links
from lemonaid.messages import store, waiter
from lemonaid.watch import codex_scout, own_edits, wait_state, waiter_lock

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
    stop_check.handle(json.dumps({"session_id": _THREAD}), grace=0.0, harness="codex")
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
    assert "lemonaid watch --self --push" in blocked["reason"]


def test_a_codex_parent_whose_scout_starts_may_stop(capsys, monkeypatch):
    parent = _briefed()
    child = brief_store.briefs_dir() / "child.md"
    child.write_text("# child\n\nStatus: working\n")
    with db.connect() as conn:
        links.set_parent(conn, identity.ensure(conn, child), parent)
    monkeypatch.setattr(codex_scout, "ensure_for", lambda thread, path: thread == _THREAD)

    assert _stop(capsys) is None


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_session_start_arms_one_waiter(harness):
    session = _THREAD if harness == "codex" else "abcd1234-0000"
    _briefed(
        channel=f"codex:{_THREAD}" if harness == "codex" else "claude:abcd1234",
        body="\n## Waiters\n\n- `lemonaid watch pr --wait 12 --once`\n",
    )

    text = session_start.context({"session_id": session}, harness)

    assert (own_edits.writer_dir(own_edits.root(), f"{harness}-{session}") / "brief").is_file()
    assert "lemonaid watch --self" in text
    assert "--status" in text
    assert ("--codex-thread" in text) is (harness == "codex")


def test_session_start_says_nothing_without_a_brief():
    marker = own_edits.writer_dir(own_edits.root(), f"codex-{_THREAD}") / "brief"
    marker.parent.mkdir(parents=True)
    marker.write_text("previous brief")
    assert session_start.context({"session_id": _THREAD}, "codex") == ""
    assert not marker.exists()


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_unified_waiter_satisfies_parent_stop_check(monkeypatch, harness):
    session = _THREAD if harness == "codex" else "abcd1234-0000"
    channel = f"codex:{_THREAD}" if harness == "codex" else "claude:abcd1234"
    parent = _briefed(channel=channel)
    child = brief_store.briefs_dir() / "child.md"
    child.write_text("# child\n")
    with db.connect() as conn:
        links.set_parent(conn, identity.ensure(conn, child), parent)
    wait_state.lock_path(parent).parent.mkdir(parents=True)
    with waiter_lock.acquire(wait_state.lock_path(parent)):
        assert stop_check.reason_to_block({"session_id": session}, 0, harness) == ""


def test_done_sessions_still_get_wait_guidance():
    _briefed()
    with db.connect() as conn:
        path = attached.by_channel(conn, [f"codex:{_THREAD}"])[f"codex:{_THREAD}"]
    path.write_text(path.read_text().replace("Status: working", "Status: done"))
    assert "lemonaid watch --self" in session_start.context({"session_id": _THREAD}, "codex")


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_inbox_only_is_not_enough_for_a_brief_with_pr_subscriptions(capsys, harness):
    session = _THREAD if harness == "codex" else "abcd1234-0000"
    channel = f"codex:{_THREAD}" if harness == "codex" else "claude:abcd1234"
    lemon_id = _briefed(
        channel=channel,
        body="\n## Watching\n\n- `lemonaid watch pr --wait https://github.com/o/r/pull/12`\n",
    )
    with waiter.armed(store.inbox_for_id(lemon_id)):
        reason = stop_check.reason_to_block({"session_id": session}, 0, harness)
    assert "lemonaid watch --self" in reason
    assert "--keep-subscriptions" in reason


def test_a_claude_lemon_with_a_push_scout_is_told_what_lemonaid_does_for_it(monkeypatch):
    _briefed(channel="claude:abcd1234")
    monkeypatch.setattr(session_start, "_pushed", lambda path, session_id: True)

    text = session_start.context({"session_id": "abcd1234-0000"}, "claude")

    assert "lemonaid is watching for you" in text
    assert "don't" not in text.lower()
    assert "--codex-thread" not in text


def test_a_codex_lemon_with_a_push_scout_is_told_what_lemonaid_does_for_it(monkeypatch):
    _briefed()
    monkeypatch.setattr(codex_scout, "ensure_for", lambda thread, path: thread == _THREAD)

    text = session_start.context({"session_id": _THREAD}, "codex")

    assert "lemonaid is watching for you" in text
    assert "--codex-thread" not in text
    assert "rearm" not in text


def test_the_codex_fallback_text_names_no_claude_mechanism():
    _briefed()

    text = session_start.context({"session_id": _THREAD}, "codex")

    assert "`lemonaid watch --self --push` with escalated permissions" in text
    assert "Bash" not in text
