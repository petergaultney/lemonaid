"""The cutover waits for the reserved window and its real channel."""

import argparse
import time
from unittest.mock import Mock

import pytest

from lemonaid.brief import (
    attached,
    handoff_cli,
    handoff_coordinator,
    handoff_launch,
    handoff_state,
    handoff_tmux,
)
from lemonaid.config import Config, TmuxSessionConfig
from lemonaid.inbox import db
from lemonaid.launch import window

from .shared import requested


def test_changed_target_pane_leaves_old_channel_active(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    conn.execute(
        """UPDATE brief_handoffs SET phase = 'launched', target = 'codex:new',
           target_window = '3', target_window_id = '@3', target_pane_id = '%3',
           ready = 1, accepted = 1 WHERE token = ?""",
        (row["token"],),
    )
    conn.commit()
    monkeypatch.setattr(
        handoff_tmux,
        "pane",
        lambda _session, index: ("%2", "@2") if index == "2" else ("%other", "@3"),
    )
    report = handoff_coordinator.advance(conn, row["token"])
    assert report["missing"] == ["new pane changed; cutover stopped"]
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path
    assert db.get_by_channel(conn, "claude:old", unread_only=False).status != "archived"


def test_failed_launch_leaves_old_channel_active(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    monkeypatch.setattr(handoff_tmux, "pane", lambda *_: ("%2", "@2"))

    def fail(_conn, _row):
        raise ValueError("launch failed")

    monkeypatch.setattr(handoff_launch, "run", fail)
    with pytest.raises(ValueError, match="launch failed"):
        handoff_coordinator.advance(conn, row["token"])

    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path
    assert db.get_by_channel(conn, "claude:old", unread_only=False).status != "archived"


def test_first_turn_accept_waits_for_codex_notification_without_tui_location(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    conn.execute("DELETE FROM notifications WHERE channel = 'codex:new'")
    conn.execute(
        """UPDATE brief_handoffs SET phase = 'launched', target_window = '3',
           target_window_id = '@3', target_pane_id = '%3', ready = 1 WHERE token = ?""",
        (row["token"],),
    )
    conn.commit()
    assert handoff_state.bind_target(conn, row["token"], "codex:new")
    handoff_state.acknowledge(conn, row["token"], "codex:new", "accept")
    monkeypatch.setattr(
        handoff_tmux, "pane", lambda _session, index: ("%2", "@2") if index == "2" else ("%3", "@3")
    )
    monkeypatch.setattr(handoff_tmux, "close_old", lambda _row: True)
    assert "has not registered" in handoff_coordinator.advance(conn, row["token"])["missing"][0]
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path

    db.add(
        conn,
        "codex:new",
        "First turn done",
        metadata={"session_id": "new", "cwd": str(path.parent)},
    )
    assert handoff_coordinator.advance(conn, row["token"])["phase"] == "complete"
    assert attached.by_channel(conn, ["codex:new"])["codex:new"] == path


def test_failed_send_retries_in_the_same_reserved_window(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    config = Config(
        tmux_session=TmuxSessionConfig(
            templates={"codex": ["", "codex --no-daemon"]}, resume_window=1
        )
    )
    monkeypatch.setattr(handoff_launch, "load_config", lambda: config)
    monkeypatch.setattr(handoff_tmux, "target_index", lambda _session: "3")
    monkeypatch.setattr(
        handoff_tmux, "pane", lambda _session, index: ("%2", "@2") if index == "2" else ("%3", "@3")
    )
    monkeypatch.setattr(handoff_tmux, "current_command", lambda _pane: "zsh")
    opened = Mock(return_value=(window.Pane("%3", "@3"), ""))
    sent = Mock(side_effect=["send failed", ""])
    monkeypatch.setattr(window, "open_window", opened)
    monkeypatch.setattr(window, "run", sent)

    with pytest.raises(ValueError, match="send failed"):
        handoff_coordinator.advance(conn, row["token"])
    assert handoff_state.get(conn, row["token"])["phase"] == "prepared"
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path

    assert handoff_coordinator.advance(conn, row["token"])["phase"] == "launched"
    assert opened.call_count == 1
    assert sent.call_count == 2


def test_timeout_prompts_source_once_and_restores_waiter_enforcement(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    conn.execute(
        "UPDATE brief_handoffs SET deadline = ? WHERE token = ?", (time.time() - 1, row["token"])
    )
    conn.commit()
    prompt = Mock(return_value=True)
    monkeypatch.setattr(handoff_tmux, "prompt_source_to_rearm", prompt)

    first = handoff_coordinator.advance(conn, row["token"])
    second = handoff_coordinator.advance(conn, row["token"])
    assert "prompted to rearm" in first["missing"][0]
    assert second["missing"] == first["missing"]
    prompt.assert_called_once()
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path
    assert not handoff_state.pending_source(conn, path, "claude:old", time.time())

    handoff_state.request(
        conn, path, "claude:old", "codex", "work", "2", "@2", "%2", "claude", time.time() + 600
    )
    assert handoff_state.pending_source(conn, path, "claude:old", time.time())


def test_watcher_failure_prompts_source_to_rearm(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    monkeypatch.setattr(db, "get_db_path", lambda: path.parent / "inbox.db")
    prompt = Mock(return_value=True)
    monkeypatch.setattr(handoff_tmux, "prompt_source_to_rearm", prompt)
    monkeypatch.setattr(handoff_coordinator, "advance", Mock(side_effect=ValueError("failed")))

    handoff_cli._cmd(argparse.Namespace(watch=True, token=row["token"]))

    prompt.assert_called_once()
    assert "prompted to rearm" in handoff_state.get(conn, row["token"])["error"]
    assert not handoff_state.pending_source(conn, path, "claude:old", time.time())
