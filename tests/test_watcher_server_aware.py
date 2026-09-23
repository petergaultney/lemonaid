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
            argv, 0, stdout="/dev/ttys001|relay|%1|1000\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _run)
    assert handlers.check_pane_exists_by_tty("/dev/ttys001", "tmux", "/tmp/tmux-1/other") is True
    assert asked[0][:3] == ["tmux", "-S", "/tmp/tmux-1/other"]


def test_a_session_on_another_server_is_not_archived(monkeypatch):
    """The regression: its pane is alive, just not on the server the watcher sees."""
    archived: list[str] = []
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name: True)

    # The pane is alive on its server. pane_locations includes the tty for that socket.
    socket = "/tmp/tmux-1/other"
    sockets = {"claude:elsewhere": socket}
    pane_locations = {socket: {"/dev/ttys001": ("relay", "0")}}

    watcher._archive_stale_sessions(
        [_active("claude:elsewhere", "/dev/ttys001")],
        archived.append,
        sockets,
        pane_locations,
    )

    assert archived == []


def test_a_session_with_no_recorded_socket_is_checked_via_default_server(monkeypatch):
    """Backward compatible: rows written before this keep the old behaviour.

    No socket recorded means the channel maps to socket=None. The pane_locations
    for socket=None includes the tty, so it survives.
    """
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name: True)
    archived: list[str] = []

    # No socket for this channel -> looks up pane_locations[None]
    pane_locations = {None: {"/dev/ttys001": ("session", "0")}}
    watcher._archive_stale_sessions(
        [_active("claude:old", "/dev/ttys001")],
        archived.append,
        {},
        pane_locations,
    )

    assert archived == []


def test_a_genuinely_dead_pane_is_still_archived(monkeypatch):
    """The socket must not turn the archiver off - only aim it."""
    archived: list[str] = []

    # The server answered (socket key present) but the tty is not in the listing.
    socket = "/tmp/tmux-1/other"
    sockets = {"claude:gone": socket}
    pane_locations = {socket: {}}  # server answered, pane not there

    watcher._archive_stale_sessions(
        [_active("claude:gone", "/dev/ttys001")],
        archived.append,
        sockets,
        pane_locations,
    )

    assert archived == ["claude:gone"]


def test_an_automatic_archive_logs_its_decision_and_evidence(monkeypatch):
    logged: list[str] = []
    monkeypatch.setattr(
        watcher._log,
        "info",
        lambda message, *args: logged.append(message % args),
    )
    socket = "/tmp/tmux-1/other"

    watcher._archive_stale_sessions(
        [_active("claude:gone", "/dev/ttys001")],
        lambda _channel: None,
        {"claude:gone": socket},
        {socket: {"/dev/ttys002": ("relay", "0")}},
    )

    assert len(logged) == 1
    event = logged[0]
    for field in (
        "auto-archive",
        "channel=claude:gone",
        "reason=pane-gone",
        "session_id=sid",
        "tty=/dev/ttys001",
        "source=tmux",
        f"socket={socket}",
        "cwd='/tmp'",
        "created_at=0.000",
        "known_panes=['/dev/ttys002']",
    ):
        assert field in event


def test_a_dead_server_is_not_an_answer(monkeypatch):
    """`tmux -S` on a socket that is gone exits non-zero, which must read as
    "cannot tell" rather than "no pane" - otherwise a server that never comes
    back archives every session it hosted."""

    def _run(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv, stderr="error connecting")

    monkeypatch.setattr(subprocess, "run", _run)
    assert handlers.check_pane_exists_by_tty("/dev/ttys001", "tmux", "/tmp/gone") is None
    assert watcher._check_pane_exists("/dev/ttys001", "tmux", "/tmp/gone") is True


def test_a_dead_server_archives_nothing(monkeypatch):
    """End to end: server unreachable -> socket key absent from pane_locations."""
    archived: list[str] = []
    monkeypatch.setattr(watcher, "is_process_running_on_tty", lambda tty, name: True)

    socket = "/tmp/tmux-1/gone"
    sockets = {"claude:a": socket}
    # Socket not in pane_locations at all -> server couldn't be reached -> assume alive
    pane_locations: dict = {}

    watcher._archive_stale_sessions(
        [_active("claude:a", "/dev/ttys001")],
        archived.append,
        sockets,
        pane_locations,
    )

    assert archived == []


def _listing(monkeypatch, stdout: str) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr=""),
    )


def test_a_reused_tty_does_not_resurrect_an_old_session(monkeypatch):
    """tty names are recycled. After a reboot a recorded tty usually names some
    unrelated pane, which otherwise reads as the old session still running."""
    _listing(monkeypatch, "/dev/ttys001|relay|%1|2000\n")  # session created after the record

    assert navigation.get_pane_for_tty("/dev/ttys001", None, not_after=1000) == (None, None)


def test_a_pane_older_than_the_record_is_the_session(monkeypatch):
    """The session was there before the notification, so it is the one meant."""
    _listing(monkeypatch, "/dev/ttys001|relay|%1|500\n")

    assert navigation.get_pane_for_tty("/dev/ttys001", None, not_after=1000) == ("relay", "%1")


def test_without_a_cutoff_any_pane_on_that_tty_matches(monkeypatch):
    """Callers that have no timestamp keep the old behaviour."""
    _listing(monkeypatch, "/dev/ttys001|relay|%1|9999\n")

    assert navigation.get_pane_for_tty("/dev/ttys001") == ("relay", "%1")
