"""Asking the right tmux server whether a pane is still there.

Every tmux command goes to the server the calling process is attached to unless
told otherwise. A session recorded on another server is simply absent from this
one's listing, which is indistinguishable from the pane having been closed - so
the watcher archived live sessions whenever it ran somewhere else.
"""

import subprocess

from lemonaid import handlers
from lemonaid.lemon_watchers import watcher
from lemonaid.tmux import navigation


def _active(channel: str, tty: str) -> tuple:
    return (channel, "sid", "/tmp", 0.0, False, tty, "message", "tmux")


def test_a_socket_aims_the_command_at_that_server():
    assert navigation.server_args("/tmp/tmux-1/other") == ["tmux", "-S", "/tmp/tmux-1/other"]


def test_no_socket_uses_the_attached_server():
    """Old rows have no socket recorded, and must keep working as they did."""
    assert navigation.server_args(None) == ["tmux"]


def test_the_pane_check_asks_the_recorded_server(monkeypatch):
    asked: list[list[str]] = []

    def _run(argv, **kwargs):
        asked.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout="/dev/ttys001|relay|%1\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _run)
    assert handlers.check_pane_exists_by_tty("/dev/ttys001", "tmux", "/tmp/tmux-1/other") is True
    assert asked[0][:3] == ["tmux", "-S", "/tmp/tmux-1/other"]


def test_a_session_on_another_server_is_not_archived(monkeypatch):
    """The regression: its pane is alive, just not on the server the watcher sees."""
    archived: list[str] = []

    def _pane_exists(tty, switch_source, socket=None):
        return socket == "/tmp/tmux-1/other"  # only that server can see it

    monkeypatch.setattr(watcher, "_check_pane_exists", _pane_exists)
    # The second pass asks the local process table, which is a different question
    # from the one under test here.
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name: True)
    watcher._archive_stale_sessions(
        [_active("claude:elsewhere", "/dev/ttys001")],
        archived.append,
        {"claude:elsewhere": "/tmp/tmux-1/other"},
    )

    assert archived == []


def test_a_session_with_no_recorded_socket_is_checked_as_before(monkeypatch):
    """Backward compatible: rows written before this keep the old behaviour."""
    seen: list[str | None] = []

    def _pane_exists(tty, switch_source, socket=None):
        seen.append(socket)
        return True

    monkeypatch.setattr(watcher, "_check_pane_exists", _pane_exists)
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name: True)
    watcher._archive_stale_sessions([_active("claude:old", "/dev/ttys001")], lambda c: None, {})

    assert seen == [None]


def test_a_genuinely_dead_pane_is_still_archived(monkeypatch):
    """The socket must not turn the archiver off - only aim it."""
    archived: list[str] = []
    monkeypatch.setattr(watcher, "_check_pane_exists", lambda tty, src, socket=None: False)
    watcher._archive_stale_sessions(
        [_active("claude:gone", "/dev/ttys001")],
        archived.append,
        {"claude:gone": "/tmp/tmux-1/other"},
    )

    assert archived == ["claude:gone"]


def test_a_dead_server_is_not_an_answer(monkeypatch):
    """`tmux -S` on a socket that is gone exits non-zero, which must read as
    "cannot tell" rather than "no pane" - otherwise a server that never comes
    back archives every session it hosted."""

    def _run(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv, stderr="error connecting")

    monkeypatch.setattr(subprocess, "run", _run)
    assert handlers.check_pane_exists_by_tty("/dev/ttys001", "tmux", "/tmp/gone") is None
    assert watcher._check_pane_exists("/dev/ttys001", "tmux", "/tmp/gone") is True
