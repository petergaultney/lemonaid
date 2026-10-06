"""Manual handoff keeps the source until a real target accepts."""

import argparse
import json
import os
import shlex
import subprocess
import sys
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
from lemonaid.inbox import db, pins


def _requested(conn, path):
    row = handoff_state.request(
        conn, path, "claude:old", "codex", "", "", "", "", str(path.parent), time.time() + 600
    )
    path.write_text(
        path.read_text().replace("Old notes.", f"New notes.\nHandoff-Ready: {row['token']}")
    )
    return row


def test_source_without_tmux_uses_inbox_working_directory(setup, monkeypatch):
    conn, path = setup
    monkeypatch.setattr(handoff_tmux, "pane", lambda *_args: ("", ""))
    source = handoff_coordinator.source(conn, "claude:old", "codex")
    assert source == (path, "", "", "", "", str(path.parent))


def test_source_identifies_its_tty_with_other_panes_present(setup, monkeypatch):
    conn, path = setup
    metadata = {
        "session_id": "old",
        "cwd": str(path.parent),
        "tty": "/dev/ttys2",
        "tmux_session": "work",
        "tmux_window": "2",
    }
    conn.execute(
        "UPDATE notifications SET metadata = ? WHERE channel = 'claude:old'",
        (json.dumps(metadata),),
    )
    conn.commit()
    monkeypatch.setattr(handoff_tmux, "pane_for_tty", lambda *_: ("%2", "@2"))
    monkeypatch.setattr(handoff_tmux, "current_command", lambda *_: "claude")
    assert handoff_coordinator.source(conn, "claude:old", "codex") == (
        path,
        "work",
        "2",
        "@2",
        "%2",
        "claude",
    )


def test_manual_lifecycle_transfers_state_without_touching_tmux(setup, monkeypatch):
    conn, path = setup
    row = _requested(conn, path)
    pane = Mock(side_effect=AssertionError("tmux queried"))
    monkeypatch.setattr(handoff_tmux, "pane", pane)
    db.snooze(conn, db.get_by_channel(conn, "claude:old", unread_only=False).id, time.time() + 300)

    report = handoff_coordinator.advance(conn, row["token"])
    assert report["phase"] == "launched"
    assert report["start_command"].startswith(f"cd {path.parent} && env LEMONAID_HANDOFF_TOKEN=")
    assert "codex" in report["start_command"]
    assert f"accept {row['token']}" in report["start_prompt"]
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path
    assert handoff_coordinator.advance(conn, row["token"])["phase"] == "launched"

    monkeypatch.setenv("LEMONAID_HANDOFF_TOKEN", row["token"])
    monkeypatch.setenv("CODEX_THREAD_ID", "new")
    monkeypatch.delenv("LEMONAID_CHANNEL", raising=False)
    monkeypatch.setattr(handoff_cli.db, "connect", lambda: nullcontext(conn))
    monkeypatch.setattr(handoff_cli.subprocess, "Popen", Mock())
    handoff_cli._cmd(argparse.Namespace(watch=False, to=None, token=row["token"], action="accept"))
    assert attached.by_channel(conn, ["codex:new"])["codex:new"] == path
    assert db.get_by_channel(conn, "codex:new", unread_only=False).name == "Manual name"
    assert db.get_by_channel(conn, "codex:new", unread_only=False).status == "snoozed"
    assert pins.pinned_positions(conn) == {"codex:new": 10.0}
    assert (
        conn.execute("SELECT emoji FROM session_emoji WHERE channel = 'codex:new'").fetchone()[0]
        == "🍋"
    )
    assert db.get_by_channel(conn, "claude:old", unread_only=False).status == "archived"
    pane.assert_not_called()


def test_manual_command_uses_configured_harness_line(setup, monkeypatch):
    conn, path = setup
    row = _requested(conn, path)
    monkeypatch.setattr(
        handoff_launch,
        "load_config",
        lambda: Config(
            tmux_session=TmuxSessionConfig(
                templates={"codex": ["", "/opt/team/codex-wrapper --profile team"]},
                resume_window=1,
            )
        ),
    )
    command = handoff_coordinator.advance(conn, row["token"])["start_command"]
    assert "env LEMONAID_HANDOFF_TOKEN=" in command
    assert "/opt/team/codex-wrapper --profile team" in command
    assert "## Handoff" in command


def test_manual_command_passes_handoff_prompt_as_argument(setup, monkeypatch):
    conn, path = setup
    row = _requested(conn, path)
    argv_path = path.parent / "target-argv.json"
    target = path.parent / "dummy-target.py"
    target.write_text(
        "import json, sys\n" f"open({str(argv_path)!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
    )
    monkeypatch.setattr(
        handoff_launch,
        "configured_line",
        lambda *_: f"{shlex.quote(sys.executable)} {shlex.quote(str(target))}",
    )
    report = handoff_coordinator.advance(conn, row["token"])

    subprocess.run(
        report["start_command"],
        shell=True,
        check=True,
        env={key: value for key, value in os.environ.items() if key != "LEMONAID_PROMPT"},
    )
    assert json.loads(argv_path.read_text()) == [report["start_prompt"]]


def test_manual_status_keeps_source_resume_command(setup):
    conn, path = setup
    row = _requested(conn, path)
    conn.execute(
        "UPDATE brief_handoffs SET resume_line = ?, resume_cwd = ? WHERE token = ?",
        ("lemonaid claude resume old", str(path.parent), row["token"]),
    )
    conn.commit()
    report = handoff_coordinator.advance(conn, row["token"])
    assert report["resume_command"] == f"cd {path.parent} && lemonaid claude resume old"


def test_manual_timeout_keeps_source_and_never_prompts_tmux(setup, monkeypatch):
    conn, path = setup
    row = _requested(conn, path)
    conn.execute(
        "UPDATE brief_handoffs SET deadline = ? WHERE token = ?", (time.time() - 1, row["token"])
    )
    conn.commit()
    prompt = Mock(side_effect=AssertionError("tmux prompted"))
    monkeypatch.setattr(handoff_tmux, "prompt_source_to_rearm", prompt)
    report = handoff_coordinator.advance(conn, row["token"])
    assert "rearm its waiters" in report["missing"][0]
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path
    assert not handoff_state.pending_source(conn, path, "claude:old", time.time())
    prompt.assert_not_called()


def test_exited_source_keeps_active_snooze_until_manual_accept(setup, monkeypatch):
    conn, path = setup
    row = _requested(conn, path)
    old = db.get_by_channel(conn, "claude:old", unread_only=False)
    until = time.time() + 300
    db.snooze(conn, old.id, until)
    handoff_coordinator.advance(conn, row["token"])
    conn.execute("UPDATE notifications SET status = 'archived' WHERE channel = 'claude:old'")
    conn.commit()

    monkeypatch.setenv("LEMONAID_HANDOFF_TOKEN", row["token"])
    monkeypatch.setenv("CODEX_THREAD_ID", "new")
    monkeypatch.delenv("LEMONAID_CHANNEL", raising=False)
    monkeypatch.setattr(handoff_cli.db, "connect", lambda: nullcontext(conn))
    handoff_cli._cmd(argparse.Namespace(watch=False, to=None, token=row["token"], action="accept"))

    new = db.get_by_channel(conn, "codex:new", unread_only=False)
    assert (new.status, new.snooze_until) == ("snoozed", until)
    assert new.name == "Manual name"
    assert pins.pinned_positions(conn) == {"codex:new": 10.0}
    assert (
        conn.execute("SELECT emoji FROM session_emoji WHERE channel = 'codex:new'").fetchone()[0]
        == "🍋"
    )
    assert attached.by_channel(conn, ["codex:new"])["codex:new"] == path


def test_desktop_target_accepts_with_native_session_id_and_token_argument(setup, monkeypatch):
    conn, path = setup
    row = _requested(conn, path)
    handoff_coordinator.advance(conn, row["token"])
    monkeypatch.setenv("CODEX_THREAD_ID", "new")
    monkeypatch.delenv("LEMONAID_HANDOFF_TOKEN", raising=False)
    monkeypatch.delenv("LEMONAID_CHANNEL", raising=False)
    monkeypatch.setattr(handoff_cli.db, "connect", lambda: nullcontext(conn))

    handoff_cli._cmd(argparse.Namespace(watch=False, to=None, token=row["token"], action="accept"))
    assert handoff_coordinator.advance(conn, row["token"])["phase"] == "complete"
    assert attached.by_channel(conn, ["codex:new"])["codex:new"] == path


def test_accept_binds_harness_id_and_waits_for_its_inbox_row(setup, monkeypatch, capsys):
    conn, path = setup
    row = _requested(conn, path)
    conn.execute("DELETE FROM notifications WHERE channel = 'codex:new'")
    conn.commit()
    handoff_coordinator.advance(conn, row["token"])
    monkeypatch.setattr(handoff_cli.db, "connect", lambda: nullcontext(conn))
    monkeypatch.setattr(handoff_cli.subprocess, "Popen", Mock())
    monkeypatch.setenv("CODEX_THREAD_ID", "new")
    monkeypatch.setenv("LEMONAID_HANDOFF_TOKEN", "wrong")
    monkeypatch.delenv("LEMONAID_CHANNEL", raising=False)
    args = argparse.Namespace(watch=False, to=None, token=row["token"], action="accept")
    with pytest.raises(SystemExit):
        handoff_cli._cmd(args)
    assert "Accept needs" in capsys.readouterr().err
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path

    monkeypatch.setenv("LEMONAID_HANDOFF_TOKEN", row["token"])
    handoff_cli._cmd(args)
    assert "has not registered" in capsys.readouterr().out
    assert handoff_state.get(conn, row["token"])["target"] == "codex:new"
    assert attached.by_channel(conn, ["claude:old"])["claude:old"] == path

    db.add(conn, "codex:new", "New text", metadata={"session_id": "new", "cwd": str(path.parent)})
    assert handoff_coordinator.advance(conn, row["token"])["phase"] == "complete"
    assert attached.by_channel(conn, ["codex:new"])["codex:new"] == path
