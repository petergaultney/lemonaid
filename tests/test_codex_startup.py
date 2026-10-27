"""A Codex lemon is in the inbox, with its waiting brief, from its SessionStart hook."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from lemonaid.brief import attached
from lemonaid.brief import store as brief_store
from lemonaid.codex import location, notify, startup, utils
from lemonaid.hooks import session_start
from lemonaid.inbox import db
from lemonaid.watch import codex_scout

_THREAD = "01a17da7-96d7-7b41-9cb6-c549f2089108"
_SUBAGENT = "01a17da8-0000-7000-8000-000000000001"
_CWD = "/work/group-bar-status-dots"


def _rollout(root: Path, thread: str, **meta: object) -> Path:
    day = datetime.fromtimestamp((UUID(thread).int >> 80) / 1000, UTC)
    directory = root / day.strftime("%Y/%m/%d")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"rollout-2026-10-27T09-58-17-{thread}.jsonl"
    payload = {"id": thread, "session_id": thread, "cwd": _CWD, **meta}
    path.write_text(json.dumps({"type": "session_meta", "payload": payload}) + "\n")
    return path


@pytest.fixture
def rollouts(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "sessions"
    root.mkdir()
    monkeypatch.setattr(utils, "get_sessions_root", lambda: root)
    monkeypatch.setattr(location.hosting, "under_app_server", lambda: False)
    monkeypatch.setattr(location, "get_tty", lambda: "/dev/ttys055")
    monkeypatch.setattr(location, "get_tmux_session_name", lambda: "group-bar-status-dots")
    monkeypatch.setattr(location, "get_tmux_window_index", lambda: "2")
    monkeypatch.setattr(location, "get_tmux_socket", lambda: "/tmp/tmux-501/default")
    monkeypatch.setattr(location, "get_tmux_session_order", lambda: (100, 50, 7))
    monkeypatch.setenv("TMUX_PANE", "%694")
    for module in (startup, notify):
        monkeypatch.setattr(module, "detect_terminal_switch_source", lambda: "tmux")
        monkeypatch.setattr(module, "get_git_branch", lambda cwd: "group-bar-status-dots")
    monkeypatch.setattr(codex_scout, "ensure_for", lambda thread, path: False)
    return root


def _waiting_brief() -> Path:
    path = brief_store.briefs_dir() / "group-bar-status-dots.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# group bar status dots\n\nStatus: working\n")
    with db.connect() as conn:
        attached.attach_pending(
            conn, "group-bar-status-dots", "2", path, attached.live_channels(conn), name="Dots"
        )
    return path


def _start(rollout: Path, thread: str = _THREAD) -> str:
    return session_start.context(
        {
            "session_id": thread,
            "transcript_path": str(rollout),
            "cwd": _CWD,
            "hook_event_name": "SessionStart",
            "source": "startup",
        },
        "codex",
    )


def test_a_starting_codex_lemon_gets_its_row_and_waiting_brief(rollouts):
    path = _waiting_brief()

    text = _start(_rollout(rollouts, _THREAD))

    with db.connect() as conn:
        row = db.get_by_channel(conn, f"codex:{_THREAD}", unread_only=False)
        assert attached.by_channel(conn, [f"codex:{_THREAD}"]) == {f"codex:{_THREAD}": path}
    assert row is not None
    assert row.status == "read"
    assert row.name == "Dots"
    assert row.metadata["tty"] == "/dev/ttys055"
    assert row.metadata["tmux_pane_identity"] == ["%694", 50]
    assert row.metadata["git_branch"] == "group-bar-status-dots"
    assert f"Your brief is {path}" in text


def test_the_first_turn_end_updates_the_same_row(rollouts):
    _waiting_brief()
    rollout = _rollout(rollouts, _THREAD)
    _start(rollout)

    notify.handle_notification(
        json.dumps({"type": "agent-turn-complete", "thread-id": _THREAD, "cwd": _CWD})
    )

    with db.connect() as conn:
        rows = conn.execute(
            "SELECT channel, status FROM notifications WHERE channel LIKE 'codex:%'"
        ).fetchall()
        assert attached.by_channel(conn, [f"codex:{_THREAD}"])
    assert [tuple(r) for r in rows] == [(f"codex:{_THREAD}", "unread")]


def test_a_spawned_thread_gets_no_row(rollouts):
    rollout = _rollout(
        rollouts,
        _SUBAGENT,
        source={"subagent": {"thread_spawn": {"parent_thread_id": _THREAD, "depth": 1}}},
        thread_source="subagent",
        parent_thread_id=_THREAD,
    )

    _start(rollout, _SUBAGENT)

    with db.connect() as conn:
        assert db.get_by_channel(conn, f"codex:{_SUBAGENT}", unread_only=False) is None


def test_a_resumed_thread_keeps_what_its_row_already_knew(rollouts):
    rollout = _rollout(rollouts, _THREAD)
    with db.connect() as conn:
        db.add(conn, f"codex:{_THREAD}", "Waiting", metadata={"model": "gpt-6.1-sol"})
        db.archive_channel(conn, f"codex:{_THREAD}", "test")

    startup.register({"session_id": _THREAD, "transcript_path": str(rollout), "source": "resume"})

    with db.connect() as conn:
        row = db.get_by_channel(conn, f"codex:{_THREAD}", unread_only=False)
    assert row is not None
    assert row.status == "read"
    assert row.metadata["model"] == "gpt-6.1-sol"
    assert row.metadata["session_start_source"] == "resume"
