"""Codex subagents and approval reviewers never displace the session that spawned them.

They run in the parent's terminal, so a row of their own shares the parent's
tty, and the watcher archives the older of two sessions on one tty: the parent.
"""

import json
import os
from pathlib import Path

import pytest

from lemonaid.codex import notify as codex_notify
from lemonaid.codex import utils
from lemonaid.inbox import db
from lemonaid.lemon_watchers import watcher

_CWD = "/work/project"
_TTY = "/dev/ttys054"
_PARENT = "01a0ca2f-b94c-7322-b662-e7f20f7c862f"
_SUBAGENT = "02b0e8ca-9e01-74d1-99f6-5f302c6cfd7c"
_GUARDIAN = "03c0e8ca-e160-75d2-8612-69cbd966da4d"


def _write_session(root: Path, thread_id: str, **meta: object) -> Path:
    path = root / f"rollout-2026-09-28T12-00-00-{thread_id}.jsonl"
    payload = {"id": thread_id, "session_id": _PARENT, "cwd": _CWD, **meta}
    path.write_text(json.dumps({"type": "session_meta", "payload": payload}) + "\n")
    return path


@pytest.fixture
def sessions(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "sessions"
    root.mkdir()
    monkeypatch.setattr(utils, "get_sessions_root", lambda: root)
    monkeypatch.setattr(codex_notify, "get_tty", lambda: _TTY)
    monkeypatch.setattr(codex_notify.hosting, "under_app_server", lambda: False)
    monkeypatch.setattr(codex_notify, "detect_terminal_switch_source", lambda: "tmux")
    monkeypatch.setattr(codex_notify, "get_git_branch", lambda cwd: None)

    _write_session(root, _PARENT, source="cli", thread_source="user")
    _write_session(
        root,
        _SUBAGENT,
        source={"subagent": {"thread_spawn": {"parent_thread_id": _PARENT, "depth": 1}}},
        thread_source="subagent",
        parent_thread_id=_PARENT,
    )
    _write_session(
        root,
        _GUARDIAN,
        source={"subagent": {"other": "guardian"}},
        thread_source="guardian_review",
        parent_thread_id=_SUBAGENT,
    )
    return root


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
    watcher._archive_stale_sessions(rows, archived.append, {}, {None: {_TTY: ("hq", "2")}})

    assert [row[0] for row in rows] == [f"codex:{_PARENT}"]
    assert archived == []


def test_the_cwd_fallback_skips_a_newer_spawned_thread(sessions):
    """A notification without a thread id is resolved by cwd, to the newest rollout there."""
    parent = next(sessions.glob(f"*{_PARENT}.jsonl"))
    for path in sessions.iterdir():
        mtime = 1000.0 if path == parent else 2000.0
        os.utime(path, (mtime, mtime))

    assert utils.find_latest_session_for_cwd(_CWD) == parent


def test_a_rollout_without_session_meta_gets_no_row(sessions):
    """It could be a subagent's, and a row of its own would displace the parent."""
    _turn_complete(_PARENT)
    unreadable = "04d0e8ca-0000-7000-8000-000000000000"
    (sessions / f"rollout-2026-09-28T12-00-00-{unreadable}.jsonl").write_text("")

    _turn_complete(unreadable)

    assert [row[0] for row in _watcher_rows()] == [f"codex:{_PARENT}"]
