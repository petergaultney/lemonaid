"""A tty outlives the agent session that ran on it.

Close a lemon in a shell and start another, and both notifications carry the
same tty. The newer one is the live session; the older is stale and must be
archived, or the inbox accumulates an entry per session that shell ever hosted.
"""

from lemonaid.lemon_watchers import watcher


def _row(channel: str, tty: str | None, created_at: float):
    """One row in the shape _archive_stale_sessions consumes."""
    return (channel, "sid", "/work/feat", created_at, False, tty, "msg", "tmux")


def _archiver() -> tuple[list[str], object]:
    archived: list[str] = []
    return archived, archived.append


def _panes(monkeypatch, *, alive: bool, process_running: bool) -> None:
    monkeypatch.setattr(watcher, "_check_pane_exists", lambda tty, src: alive)
    monkeypatch.setattr(
        watcher, "is_process_running_on_tty", lambda tty, name="claude": process_running
    )


def test_the_older_session_on_a_reused_tty_is_archived(monkeypatch):
    _panes(monkeypatch, alive=True, process_running=True)
    archived, archive = _archiver()

    watcher._archive_stale_sessions(
        [_row("claude:old", "/dev/ttys004", 100.0), _row("claude:new", "/dev/ttys004", 200.0)],
        archive,
    )

    assert archived == ["claude:old"]


def test_both_go_when_the_process_is_gone(monkeypatch):
    """The shell is idle, so neither session is running on it any more."""
    _panes(monkeypatch, alive=True, process_running=False)
    archived, archive = _archiver()

    watcher._archive_stale_sessions(
        [_row("claude:old", "/dev/ttys004", 100.0), _row("claude:new", "/dev/ttys004", 200.0)],
        archive,
    )

    assert sorted(archived) == ["claude:new", "claude:old"]


def test_a_dead_pane_is_archived_before_any_grouping(monkeypatch):
    _panes(monkeypatch, alive=False, process_running=True)
    archived, archive = _archiver()

    watcher._archive_stale_sessions([_row("claude:gone", "/dev/ttys004", 100.0)], archive)

    assert archived == ["claude:gone"]


def test_different_ttys_do_not_compete(monkeypatch):
    """Two live sessions in different shells are both current."""
    _panes(monkeypatch, alive=True, process_running=True)
    archived, archive = _archiver()

    watcher._archive_stale_sessions(
        [_row("claude:a", "/dev/ttys004", 100.0), _row("claude:b", "/dev/ttys005", 200.0)],
        archive,
    )

    assert archived == []


def test_a_row_without_a_tty_is_left_alone(monkeypatch):
    """Nothing here can decide anything about it - and it must not take another down."""
    _panes(monkeypatch, alive=True, process_running=True)
    archived, archive = _archiver()

    watcher._archive_stale_sessions(
        [_row("claude:no-tty", None, 100.0), _row("claude:live", "/dev/ttys004", 200.0)],
        archive,
    )

    assert archived == []
