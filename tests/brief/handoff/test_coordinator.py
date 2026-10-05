"""Sequential handoff preserves the pane and recovers a failed target."""

import argparse
import time
from contextlib import nullcontext
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

from .shared import requested


def test_launch_replaces_source_process_in_same_pane(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    config = Config(
        tmux_session=TmuxSessionConfig(
            templates={"codex": ["", "codex --no-daemon"]}, resume_window=1
        )
    )
    monkeypatch.setattr(handoff_launch, "load_config", lambda: config)
    monkeypatch.setattr(handoff_tmux, "has_pane", lambda *_: True)
    monkeypatch.setattr(handoff_tmux, "current_command", lambda _pane: "claude")
    monkeypatch.setattr(handoff_tmux, "remain_on_exit", lambda _pane: "off")
    monkeypatch.setattr(handoff_tmux, "set_remain_on_exit", lambda *_: True)
    state = Mock(side_effect=[("300", False), ("300", False), ("400", False), ("400", False)])
    monkeypatch.setattr(handoff_tmux, "pane_process", state)
    respawn = Mock(return_value="")
    monkeypatch.setattr(handoff_tmux, "respawn", respawn)
    report = handoff_coordinator.advance(conn, row["token"])
    assert report["phase"] == "launched"
    assert report["old_pane"] == report["new_pane"] == "%2"
    assert respawn.call_args.args[0] == "%2"
    assert handoff_state.get(conn, row["token"])["target_pid"] == "400"


def test_target_exit_resumes_source_in_same_pane(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    conn.execute(
        """UPDATE brief_handoffs SET phase = 'launched', target_window = '2',
           target_window_id = '@2', target_pane_id = '%2', target_pid = '400',
           remain_on_exit = 'off' WHERE token = ?""",
        (row["token"],),
    )
    conn.commit()
    monkeypatch.setattr(handoff_tmux, "pane_process", lambda *_: ("400", True))
    resumed = Mock(return_value=True)
    monkeypatch.setattr(handoff_tmux, "resume_source", resumed)
    monkeypatch.setattr(handoff_tmux, "set_remain_on_exit", lambda *_: True)
    report = handoff_coordinator.advance(conn, row["token"])
    assert report["phase"] == "failed"
    assert "resumed" in report["missing"][0]
    resumed.assert_called_once()
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path


def test_target_process_change_stops_transfer(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    conn.execute(
        """UPDATE brief_handoffs SET phase = 'launched', target = 'codex:new',
           target_window = '2', target_window_id = '@2', target_pane_id = '%2',
           target_pid = '400', ready = 1, accepted = 1 WHERE token = ?""",
        (row["token"],),
    )
    conn.commit()
    monkeypatch.setattr(handoff_tmux, "pane_process", lambda *_: ("other", False))
    assert "pane changed" in handoff_coordinator.advance(conn, row["token"])["missing"][0]
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path


def test_stale_row_on_reused_tty_cannot_become_target(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    conn.execute(
        """UPDATE brief_handoffs SET phase = 'launched', target_window = '2',
           target_window_id = '@2', target_pane_id = '%2', target_pid = '400',
           ready = 1 WHERE token = ?""",
        (row["token"],),
    )
    conn.commit()
    db.add(
        conn,
        "codex:stale",
        "Earlier session",
        metadata={"tmux_session": "work", "tmux_window": "2", "tty": "/dev/ttys2"},
    )
    monkeypatch.setattr(handoff_tmux, "pane_process", lambda *_: ("400", False))
    report = handoff_coordinator.advance(conn, row["token"])
    assert report["target"] is None
    assert "accept acknowledgement" in report["missing"][0]
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path


def test_accept_waits_for_notification(setup, monkeypatch):
    conn, path = setup
    row = requested(conn, path)
    conn.execute("DELETE FROM notifications WHERE channel = 'codex:new'")
    conn.execute(
        """UPDATE brief_handoffs SET phase = 'launched', target_window = '2',
           target_window_id = '@2', target_pane_id = '%2', target_pid = '400',
           remain_on_exit = 'off', ready = 1 WHERE token = ?""",
        (row["token"],),
    )
    conn.commit()
    assert handoff_state.bind_target(conn, row["token"], "codex:new")
    handoff_state.acknowledge(conn, row["token"], "codex:new", "accept")
    monkeypatch.setattr(handoff_tmux, "pane_process", lambda *_: ("400", False))
    monkeypatch.setattr(handoff_tmux, "set_remain_on_exit", lambda *_: True)
    assert "has not registered" in handoff_coordinator.advance(conn, row["token"])["missing"][0]
    db.add(
        conn,
        "codex:new",
        "First turn done",
        metadata={"session_id": "new", "cwd": str(path.parent)},
    )
    assert handoff_coordinator.advance(conn, row["token"])["phase"] == "complete"
    assert attached.by_channel(conn, ["codex:new"])["codex:new"] == path


def test_timeout_prompts_source_once(setup, monkeypatch):
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
    assert "prompted to rearm" in second["missing"][0]
    prompt.assert_called_once()
    assert not handoff_state.pending_source(conn, path, "claude:old", time.time())


def test_tmux_accept_requires_native_target_and_original_pane(setup, monkeypatch, capsys):
    conn, path = setup
    row = requested(conn, path)
    conn.execute(
        """UPDATE brief_handoffs SET phase = 'launched', target_window = '2',
           target_window_id = '@2', target_pane_id = '%2', target_pid = '400',
           remain_on_exit = 'off', ready = 1 WHERE token = ?""",
        (row["token"],),
    )
    conn.commit()
    monkeypatch.setattr(handoff_tmux, "pane_process", lambda *_: ("400", False))
    monkeypatch.setattr(handoff_tmux, "set_remain_on_exit", lambda *_: True)
    monkeypatch.setattr(handoff_cli.db, "connect", lambda: nullcontext(conn))
    monkeypatch.setattr(handoff_cli.subprocess, "Popen", Mock())
    monkeypatch.setenv("CODEX_THREAD_ID", "new")
    monkeypatch.setenv("LEMONAID_HANDOFF_TOKEN", row["token"])
    monkeypatch.delenv("LEMONAID_CHANNEL", raising=False)
    args = argparse.Namespace(watch=False, to=None, token=row["token"], action="accept")

    monkeypatch.setenv("TMUX_PANE", "%other")
    with pytest.raises(SystemExit):
        handoff_cli._cmd(args)
    assert "another pane" in capsys.readouterr().err
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path

    monkeypatch.setenv("TMUX_PANE", "%2")
    handoff_cli._cmd(args)
    assert handoff_state.get(conn, row["token"])["phase"] == "complete"
