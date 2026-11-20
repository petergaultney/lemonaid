"""Codex subagents and approval reviewers never displace the session that spawned them.

They run in the parent's terminal, so a row of their own shares the parent's
tty, and the watcher archives the older of two sessions on one tty: the parent.
"""

import json

import pytest

from lemonaid.codex import notify as codex_notify
from lemonaid.inbox import db
from lemonaid.lemon_watchers import watcher
from tests import codex_fakes

_CWD = "/work/project"
_TTY = "/dev/ttys054"
_PARENT = "01a0ca2f-b94c-7322-b662-e7f20f7c862f"
_SUBAGENT = "02b0e8ca-9e01-74d1-99f6-5f302c6cfd7c"
_GUARDIAN = "03c0e8ca-e160-75d2-8612-69cbd966da4d"


@pytest.fixture
def sessions(monkeypatch, codex_records) -> None:
    monkeypatch.setattr(codex_notify.location, "get_tty", lambda: _TTY)
    monkeypatch.setattr(codex_notify.location.hosting, "under_app_server", lambda: False)
    monkeypatch.setattr(codex_notify, "detect_terminal_switch_source", lambda: "tmux")
    monkeypatch.setattr(codex_notify, "get_git_branch", lambda cwd: None)
    codex_records[_PARENT] = codex_fakes.thread(_PARENT, _CWD)
    codex_records[_SUBAGENT] = codex_fakes.thread(_SUBAGENT, _CWD, parent=_PARENT)
    codex_records[_GUARDIAN] = codex_fakes.thread(_GUARDIAN, _CWD, parent=_SUBAGENT)


def _turn_complete(thread_id: str) -> None:
    codex_notify.handle_notification(
        json.dumps({"type": "agent-turn-complete", "thread-id": thread_id, "cwd": _CWD})
    )


def _watcher_rows() -> list[tuple]:
    with db.connect() as conn:
        return [
            (
                n.channel,
                n.metadata["session_id"],
                n.metadata["cwd"],
                n.created_at,
                n.is_unread,
                n.metadata.get("tty"),
                n.message,
                n.switch_source,
            )
            for n in db.get_active(conn, switch_source=None)
        ]


def test_spawned_threads_leave_the_open_parent_in_the_inbox(sessions, monkeypatch):
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name: True)

    _turn_complete(_PARENT)
    _turn_complete(_SUBAGENT)
    _turn_complete(_GUARDIAN)

    rows = _watcher_rows()
    archived: list[str] = []
    watcher._archive_stale_sessions(
        rows, lambda channel, why: archived.append(channel), {}, {None: {_TTY: ("hq", "2")}}
    )

    assert [row[0] for row in rows] == [f"codex:{_PARENT}"]
    assert archived == []


def test_a_thread_codex_does_not_know_gets_no_row(sessions, codex_records):
    """It could be a subagent's, and a row of its own would displace the parent."""
    _turn_complete(_PARENT)
    unreadable = "04d0e8ca-0000-7000-8000-000000000000"
    codex_records[unreadable] = None

    _turn_complete(unreadable)

    assert [row[0] for row in _watcher_rows()] == [f"codex:{_PARENT}"]
