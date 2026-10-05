"""Pane identity and rollback checks for sequential tmux handoff."""

import subprocess
from unittest.mock import Mock

from lemonaid.brief import handoff_tmux

from .shared import requested


def test_pane_for_tty_ignores_sidebar_in_same_window(monkeypatch):
    monkeypatch.setattr(
        handoff_tmux,
        "_tmux",
        lambda *_args: "%sidebar\t@2\t/dev/ttys1\t0\n%source\t@2\t/dev/ttys2\t0",
    )
    assert handoff_tmux.pane_for_tty("work", "2", "/dev/ttys2") == ("%source", "@2")


def test_pane_process_rejects_different_window(monkeypatch):
    monkeypatch.setattr(handoff_tmux, "_tmux", lambda *_: "%2\t@other\t400\t0")
    assert handoff_tmux.pane_process("%2", "@2") is None


def test_respawn_targets_exact_pane_with_environment(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(handoff_tmux, "_tmux", lambda *_: "/bin/sh")

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(handoff_tmux.subprocess, "run", run)
    assert not handoff_tmux.respawn("%2", tmp_path, "codex --no-daemon", {"TOKEN": "abc"})
    assert calls == [
        [
            "tmux",
            "respawn-pane",
            "-k",
            "-t",
            "%2",
            "-c",
            str(tmp_path),
            "-e",
            "TOKEN=abc",
            "/bin/sh",
            "-c",
            "codex --no-daemon",
        ]
    ]


def test_rollback_refuses_changed_process(setup, monkeypatch):
    conn, path = setup
    row = dict(requested(conn, path))
    row["target_pid"] = "400"
    monkeypatch.setattr(handoff_tmux, "pane_process", lambda *_: ("other", False))
    respawn = Mock(side_effect=AssertionError("would replace a stranger"))
    monkeypatch.setattr(handoff_tmux, "respawn", respawn)
    assert not handoff_tmux.resume_source(conn, row)
    respawn.assert_not_called()


def test_rollback_uses_recorded_resume_command(setup, monkeypatch):
    conn, path = setup
    row = dict(requested(conn, path))
    row.update(
        target_pid="400", resume_cwd=str(path.parent), resume_line="lemonaid claude resume old"
    )
    monkeypatch.setattr(handoff_tmux, "pane_process", lambda *_: ("400", True))
    respawn = Mock(return_value="")
    monkeypatch.setattr(handoff_tmux, "respawn", respawn)
    assert handoff_tmux.resume_source(conn, row)
    assert respawn.call_args.args[:2] == ("%2", path.parent)
    assert "lemonaid claude resume old" in respawn.call_args.args[2]
    assert "Rearm your waiters" in respawn.call_args.args[3]["LEMONAID_PROMPT"]
