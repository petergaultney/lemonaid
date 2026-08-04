"""An ambiguous directory must not spawn another session.

Recreating is right when a session is gone. It is wrong when several sessions
match, because one of them is the one wanted - adding a third to a directory
that already has two is the opposite of resolving it.
"""

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
        handlers, "_recreate_tmux_session", lambda m, c: calls.append("recreate") or True
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
