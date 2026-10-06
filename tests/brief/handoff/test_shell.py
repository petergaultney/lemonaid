"""A suspended harness can return to its shell and launch its replacement there."""

import argparse
import signal
import time
from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from lemonaid.brief import handoff_cli, handoff_shell


def test_source_job_signal_requires_same_pid_group_tty_and_start(monkeypatch):
    sent = Mock()
    monkeypatch.setattr(handoff_shell.os, "getpgrp", lambda: 99)
    monkeypatch.setattr(handoff_shell.os, "killpg", sent)
    monkeypatch.setattr(
        handoff_shell,
        "_job_process",
        lambda *_: (401, "ttys2", "T", "Mon Oct 5 20:00:00 2026", "/usr/bin/claude"),
    )
    assert handoff_shell.stopped_job(400, "/dev/ttys2", "claude") == (
        401,
        "ttys2",
        "Mon Oct 5 20:00:00 2026",
    )
    with pytest.raises(ValueError, match="not a stopped process"):
        handoff_shell.stopped_job(400, "/dev/ttys3", "claude")
    with pytest.raises(ValueError, match="not the outgoing harness"):
        handoff_shell.stopped_job(400, "/dev/ttys2", "codex")
    assert not handoff_shell.stop_job_if_same(400, 402, "ttys2", "Mon Oct 5 20:00:00 2026")
    assert not handoff_shell.stop_job_if_same(400, 401, "ttys3", "Mon Oct 5 20:00:00 2026")
    assert not handoff_shell.stop_job_if_same(400, 401, "ttys2", "old start")
    sent.assert_not_called()
    assert handoff_shell.stop_job_if_same(400, 401, "ttys2", "Mon Oct 5 20:00:00 2026")
    sent.assert_called_once_with(401, signal.SIGTERM)


def test_source_job_process_requires_harness_before_launch(monkeypatch):
    monkeypatch.setattr(handoff_shell.os, "getpgrp", lambda: 99)
    monkeypatch.setattr(
        handoff_shell,
        "_job_process",
        lambda *_: (401, "ttys2", "T", "Mon Oct 5 20:00:00 2026", "/usr/bin/python"),
    )
    with pytest.raises(ValueError, match="not the outgoing harness"):
        handoff_shell.stopped_job(400, "/dev/ttys2", "claude")


def test_process_identity_parses_ps_start_and_executable(monkeypatch):
    monkeypatch.setattr(
        handoff_shell.subprocess,
        "run",
        lambda *_args, **_kwargs: argparse.Namespace(
            returncode=0,
            stdout="401 ttys2 T Mon Oct  5 20:00:00 2026 /opt/bin/claude\n",
        ),
    )
    assert handoff_shell._job_process(400) == (
        401,
        "ttys2",
        "T",
        "Mon Oct 5 20:00:00 2026",
        "/opt/bin/claude",
    )


def test_target_command_uses_system_shell_not_callers_shell(monkeypatch):
    run = Mock(return_value=argparse.Namespace(returncode=0))
    monkeypatch.setattr(handoff_shell.subprocess, "run", run)
    monkeypatch.setenv("SHELL", "/usr/local/bin/fish")

    assert handoff_shell._run("codex --no-daemon") == 0
    run.assert_called_once_with(["/bin/sh", "-c", "codex --no-daemon"], check=False)


def test_watch_ends_stopped_job_only_after_brief_readiness(tmp_path, monkeypatch):
    reports = iter(({"phase": "requested"}, {"phase": "launched"}, {"phase": "complete"}))
    row = {"deadline": time.time() + 60, "error": ""}
    stopped = Mock(return_value=True)
    monkeypatch.setattr(handoff_cli.db, "get_db_path", lambda: tmp_path / "inbox.db")
    monkeypatch.setattr(handoff_cli.db, "connect", lambda: nullcontext(None))
    monkeypatch.setattr(handoff_cli.handoff_state, "get", lambda *_: row)
    monkeypatch.setattr(handoff_cli.handoff_coordinator, "advance", lambda *_: next(reports))
    monkeypatch.setattr(handoff_cli.handoff_shell, "stop_job_if_same", stopped)
    monkeypatch.setattr(handoff_cli.time, "sleep", lambda *_: None)
    args = argparse.Namespace(
        action="status",
        token="token",
        watch=True,
        source_pid=400,
        source_pgid=401,
        source_tty="ttys2",
        source_start="start",
    )

    handoff_cli._cmd(args)
    stopped.assert_called_once_with(400, 401, "ttys2", "start")
