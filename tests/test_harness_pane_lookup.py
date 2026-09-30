"""A row with no tty is found by the harness running on a pane's tty, not by the pane's title.

A Codex session hosted on the app-server daemon records no tty, so its row is
resolved from its directory. The pane titles there name neither agent: Codex
started as `tmux new-window ... codex` reports the shell (`python3.14` under
xonsh), and Claude reports its version. A worktree commonly holds both, the
author in one window and its reviewer in another.
"""

import subprocess

from lemonaid import handlers
from lemonaid.config import Config

_PANES = [
    "/work/feat|/dev/ttys001|feat|%1",  # emacs
    "/work/feat|/dev/ttys002|feat|%2",  # the author's Claude
    "/work/feat|/dev/ttys004|feat|%4",  # the reviewer's Codex
]
_PROCESSES = {
    "ttys001": ["emacsclient"],
    "ttys002": ["/usr/local/bin/python", "claude"],
    "ttys004": ["/usr/local/bin/python", "node", "/opt/codex/vendor/bin/codex"],
}


def _machine(monkeypatch, processes: dict[str, list[str] | str]) -> list[tuple[str, str]]:
    def _run(argv, **kwargs):
        if argv[:2] == ["tmux", "list-panes"]:
            out = "\n".join(_PANES) + "\n"
        elif argv[:2] == ["ps", "-t"]:
            found = processes.get(argv[2])
            if found is None:
                raise subprocess.TimeoutExpired(argv, 2)

            if isinstance(found, str):
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr=found)

            out = "\n".join(found) + "\n"
        else:
            raise AssertionError(f"unexpected command {argv}")

        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    switched: list[tuple[str, str]] = []
    monkeypatch.setattr(
        handlers.tmux.navigation,
        "switch_to_pane",
        lambda session, pane: switched.append((session, pane)) is None,
    )
    monkeypatch.setattr(
        handlers.tmux.recreate, "recreate", lambda m, c: switched.append(("recreated", "")) is None
    )
    return switched


def test_a_codex_row_switches_to_the_pane_running_codex(monkeypatch):
    switched = _machine(monkeypatch, _PROCESSES)

    assert handlers._handle_tmux({"channel": "codex:0199", "cwd": "/work/feat"}, Config())
    assert switched == [("feat", "%4")]


def test_a_claude_row_switches_to_the_pane_running_claude(monkeypatch):
    switched = _machine(monkeypatch, _PROCESSES)

    assert handlers._handle_tmux({"channel": "claude:abc", "cwd": "/work/feat"}, Config())
    assert switched == [("feat", "%2")]


def test_with_no_codex_running_there_the_session_is_recreated(monkeypatch):
    switched = _machine(monkeypatch, {**_PROCESSES, "ttys004": ["/usr/local/bin/python"]})

    handlers._handle_tmux({"channel": "codex:0199", "cwd": "/work/feat"}, Config())

    assert switched == [("recreated", "")]


def test_a_directory_named_after_the_harness_does_not_count(monkeypatch):
    """ps reports each executable's path, and a worktree may well be called `codex-fix`."""
    switched = _machine(
        monkeypatch,
        {**_PROCESSES, "ttys002": ["/work/codex-fix/.venv/bin/python", "claude"]},
    )

    assert handlers._handle_tmux({"channel": "codex:0199", "cwd": "/work/feat"}, Config())
    assert switched == [("feat", "%4")]


def test_two_codex_panes_in_one_session_are_not_guessed_between(monkeypatch):
    """An author and its reviewer, both Codex, in windows of one session."""
    switched = _machine(monkeypatch, {**_PROCESSES, "ttys002": ["node", "/opt/codex/bin/codex"]})

    assert not handlers._handle_tmux({"channel": "codex:0199", "cwd": "/work/feat"}, Config())
    assert switched == []


def test_a_pane_ps_cannot_read_stops_the_switch(monkeypatch):
    """Unknown is neither a match to switch to nor an absence to recreate over."""
    switched = _machine(monkeypatch, {k: v for k, v in _PROCESSES.items() if k != "ttys002"})

    assert not handlers._handle_tmux({"channel": "codex:0199", "cwd": "/work/feat"}, Config())
    assert switched == []


def test_a_ps_error_stops_the_switch(monkeypatch):
    """ps exits 1 both for a tty with no processes and for one it can't read; stderr tells them apart."""
    switched = _machine(
        monkeypatch, {**_PROCESSES, "ttys002": "ps: /dev/ttys002: No such file or directory"}
    )

    assert not handlers._handle_tmux({"channel": "codex:0199", "cwd": "/work/feat"}, Config())
    assert switched == []
