"""Pane identity and rollback checks for sequential tmux handoff."""

import shutil
import subprocess
import time
import uuid
from unittest.mock import Mock

import pytest

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


def test_returned_to_shell_checks_pane_start_command(monkeypatch):
    monkeypatch.setattr(handoff_tmux, "current_command", lambda *_: "zsh")
    monkeypatch.setattr(handoff_tmux, "_tmux", lambda *_: "/bin/zsh")
    assert handoff_tmux.returned_to_shell("%2", "300", "claude")
    assert not handoff_tmux.returned_to_shell("%2", "300", "zsh")


def test_returned_to_shell_recognizes_xonsh_python_wrapper(monkeypatch):
    monkeypatch.setattr(handoff_tmux, "current_command", lambda *_: "python3.14")
    monkeypatch.setattr(handoff_tmux, "_tmux", lambda *_: "")
    monkeypatch.setattr(
        handoff_tmux.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 0, "/bin/python3.14 -m xonsh\n", ""
        ),
    )
    assert handoff_tmux.returned_to_shell("%2", "300", "codex")


def test_dummy_harness_exits_to_original_shell_on_isolated_tmux(monkeypatch):
    if not shutil.which("tmux"):
        pytest.skip("tmux not installed")
    name = f"lemonaid-handoff-{uuid.uuid4().hex[:8]}"

    def tmux(*args):
        return subprocess.run(["tmux", "-L", name, *args], capture_output=True, text=True)

    tmux("-f", "/dev/null", "new-session", "-d", "-s", "work", "/bin/sh").check_returncode()
    try:
        socket = tmux("display-message", "-p", "-t", "work", "#{socket_path}").stdout.strip()
        monkeypatch.setenv("TMUX", f"{socket},0,0")
        pane_id = tmux("display-message", "-p", "-t", "work", "#{pane_id}").stdout.strip()
        window_id = tmux("display-message", "-p", "-t", "work", "#{window_id}").stdout.strip()
        pid, dead = handoff_tmux.pane_process(pane_id, window_id)
        assert not dead
        tmux("send-keys", "-t", pane_id, "sleep 2", "Enter").check_returncode()
        for _ in range(30):
            if handoff_tmux.current_command(pane_id) == "sleep":
                break
            time.sleep(0.05)
        assert handoff_tmux.current_command(pane_id) == "sleep"
        assert not handoff_tmux.returned_to_shell(pane_id, pid, "sleep")
        for _ in range(60):
            if handoff_tmux.returned_to_shell(pane_id, pid, "sleep"):
                break
            time.sleep(0.05)
        assert handoff_tmux.returned_to_shell(pane_id, pid, "sleep")
    finally:
        tmux("kill-server")


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
