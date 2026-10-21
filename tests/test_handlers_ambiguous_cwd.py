"""An ambiguous directory must not spawn another session.

Recreating is right when a session is gone. It is wrong when several sessions
match, because one of them is the one wanted - adding a third to a directory
that already has two is the opposite of resolving it.
"""

import pytest

from lemonaid import handlers
from lemonaid.config import Config
from lemonaid.tmux import navigation


def _resolution(monkeypatch, *, tty=(None, None), cwd=(None, None)) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(
        handlers.tmux.navigation, "get_pane_for_tty", lambda t: (calls.append("tty"), tty)[1]
    )
    monkeypatch.setattr(
        handlers.tmux.navigation,
        "get_pane_for_cwd",
        lambda c, p=None: (calls.append("cwd"), cwd)[1],
    )
    monkeypatch.setattr(
        handlers.tmux.navigation,
        "switch_to_pane",
        lambda s, p, save_current=True: calls.append(f"switch:{s}") or True,
    )
    monkeypatch.setattr(
        handlers.tmux.recreate, "recreate", lambda m, c: calls.append("recreate") or True
    )
    return calls


def test_an_ambiguous_cwd_does_not_recreate(monkeypatch):
    calls = _resolution(monkeypatch, cwd=(navigation.AMBIGUOUS, None))

    assert handlers._handle_tmux({"cwd": "/work/feat", "tty": "/dev/ttys1"}, Config()) is False
    assert "recreate" not in calls
    assert not any(c.startswith("switch") for c in calls)


def test_a_missing_session_still_recreates(monkeypatch):
    """The behavior an ambiguous match must not be confused with."""
    calls = _resolution(monkeypatch, cwd=(None, None))

    assert handlers._handle_tmux({"cwd": "/work/feat", "tty": "/dev/ttys1"}, Config()) is True
    assert "recreate" in calls


def test_a_resolved_tty_never_consults_cwd(monkeypatch):
    """The tty is unambiguous, so the directory's ambiguity cannot matter."""
    calls = _resolution(monkeypatch, tty=("feat", "%2"), cwd=(navigation.AMBIGUOUS, None))

    assert handlers._handle_tmux({"cwd": "/work/feat", "tty": "/dev/ttys1"}, Config()) is True
    assert calls == ["tty", "switch:feat"]


@pytest.mark.parametrize(
    "panes",
    [
        "/work/feat|/dev/shell|shared|%1\n",
        "/work/feat|/dev/author|shared|%1\n/work/feat|/dev/reviewer|shared|%2\n",
    ],
)
def test_identityless_codex_never_selects_cwd_or_inspects_processes(monkeypatch, panes):
    import subprocess

    def tmux_only(argv, **kwargs):
        assert argv[0] == "tmux"
        return subprocess.CompletedProcess(argv, 0, stdout=panes, stderr="")

    monkeypatch.setattr(subprocess, "run", tmux_only)
    monkeypatch.setattr(
        handlers.watcher,
        "process_on_tty",
        lambda *args: pytest.fail("click must not inspect processes"),
    )
    monkeypatch.setattr(
        handlers.tmux.navigation,
        "get_pane_for_cwd",
        lambda *args: pytest.fail("cwd cannot identify Codex"),
    )
    monkeypatch.setattr(
        handlers.tmux.recreate, "recreate", lambda *args: pytest.fail("must refuse")
    )
    assert not handlers._handle_tmux({"channel": "codex:author", "cwd": "/work/feat"}, Config())


def test_claude_cwd_fallback_still_excludes_same_directory_shell(monkeypatch):
    import subprocess

    switched = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv,
            0,
            stdout="/work/feat|/dev/agent|shared|%1\n/work/feat|/dev/shell|shared|%2\n",
            stderr="",
        ),
    )
    monkeypatch.setattr(
        handlers.watcher,
        "process_on_tty",
        lambda tty, harness: tty == "/dev/agent" and harness == "claude",
    )
    monkeypatch.setattr(
        handlers.tmux.navigation,
        "switch_to_pane",
        lambda session, pane: switched.append((session, pane)) or True,
    )
    assert handlers._handle_tmux({"channel": "claude:author", "cwd": "/work/feat"}, Config())
    assert switched == [("shared", "%1")]
