"""Codex uses saved locations; other harnesses retain process-aware cwd lookup.

Without a saved pane or usable TTY, Codex refuses without scanning processes.
Claude can still distinguish its process from shells and reviewers in one cwd.
"""

import subprocess

import pytest

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


def _machine(
    monkeypatch, processes: dict[str, list[str] | str], *, allow_ps=True
) -> list[tuple[str, str]]:
    def _run(argv, **kwargs):
        if argv[:2] == ["tmux", "list-panes"]:
            out = "\n".join(_PANES) + "\n"
        elif argv[:2] == ["ps", "-t"]:
            if not allow_ps:
                pytest.fail("identity-less Codex click must not inspect processes")
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


def test_identityless_codex_refuses_instead_of_discovering_its_harness(monkeypatch):
    switched = _machine(monkeypatch, _PROCESSES, allow_ps=False)

    assert not handlers._handle_tmux({"channel": "codex:0199", "cwd": "/work/feat"}, Config())
    assert switched == []


def test_a_claude_row_switches_to_the_pane_running_claude(monkeypatch):
    switched = _machine(monkeypatch, _PROCESSES)

    assert handlers._handle_tmux({"channel": "claude:abc", "cwd": "/work/feat"}, Config())
    assert switched == [("feat", "%2")]


def test_identityless_codex_does_not_recreate_over_an_unverified_directory(monkeypatch):
    switched = _machine(
        monkeypatch, {**_PROCESSES, "ttys004": ["/usr/local/bin/python"]}, allow_ps=False
    )

    handlers._handle_tmux({"channel": "codex:0199", "cwd": "/work/feat"}, Config())

    assert switched == []


def test_a_directory_named_after_claude_does_not_count_as_its_process(monkeypatch):
    switched = _machine(
        monkeypatch,
        {**_PROCESSES, "ttys004": ["/work/claude-fix/.venv/bin/python", "codex"]},
    )
    assert handlers._handle_tmux({"channel": "claude:abc", "cwd": "/work/feat"}, Config())
    assert switched == [("feat", "%2")]


def test_two_codex_panes_in_one_session_are_not_guessed_between(monkeypatch):
    """An author and its reviewer, both Codex, in windows of one session."""
    switched = _machine(monkeypatch, {**_PROCESSES, "ttys002": ["node", "/opt/codex/bin/codex"]})

    assert not handlers._handle_tmux({"channel": "codex:0199", "cwd": "/work/feat"}, Config())
    assert switched == []


def test_a_pane_ps_cannot_read_stops_the_switch(monkeypatch):
    """Unknown is neither a match to switch to nor an absence to recreate over."""
    switched = _machine(monkeypatch, {k: v for k, v in _PROCESSES.items() if k != "ttys002"})

    assert not handlers._handle_tmux({"channel": "claude:abc", "cwd": "/work/feat"}, Config())
    assert switched == []


def test_a_ps_error_stops_the_switch(monkeypatch):
    """ps exits 1 both for a tty with no processes and for one it can't read; stderr tells them apart."""
    switched = _machine(
        monkeypatch, {**_PROCESSES, "ttys002": "ps: /dev/ttys002: No such file or directory"}
    )

    assert not handlers._handle_tmux({"channel": "claude:abc", "cwd": "/work/feat"}, Config())
    assert switched == []
