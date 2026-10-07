"""A tty outlives the agent session that ran on it."""

from lemonaid.lemon_watchers import watcher
from lemonaid.tmux import navigation


def _row(channel: str, tty: str | None, created_at: float):
    """One row in the shape _archive_stale_sessions consumes."""
    return (channel, "sid", "/work/feat", created_at, False, tty, "msg", "tmux")


def _archiver() -> tuple[list[str], object]:
    archived: list[str] = []
    return archived, archived.append


def _pane_locations(active, *, alive: bool, order=None):
    """Build pane_locations for the default (no socket) server.

    When alive=True, every tty in `active` appears in the listing.
    When alive=False, none do.
    """
    if not alive:
        return {None: {}}

    return {
        None: {
            tty: navigation.PaneLocation("session", "0", order) for *_, tty, _, _ in active if tty
        }
    }


def _setup(monkeypatch, *, process_running: bool) -> None:
    monkeypatch.setattr(
        watcher, "is_process_running_on_tty", lambda tty, name="claude": process_running
    )


def test_a_channel_is_archived_when_its_recorded_tmux_session_is_gone(monkeypatch):
    _setup(monkeypatch, process_running=True)
    archived, archive = _archiver()
    active = [_row("claude:old", "/dev/ttys004", 100.0), _row("claude:new", "/dev/ttys004", 200.0)]
    old_order = (100, 10, 1)
    new_order = (200, 10, 2)

    watcher._archive_stale_sessions(
        active,
        archive,
        {},
        _pane_locations(active, alive=True, order=new_order),
        session_orders={"claude:old": old_order, "claude:new": new_order},
    )

    assert archived == ["claude:old"]


def test_creation_order_alone_never_displaces_a_channel_on_a_live_tty(monkeypatch):
    _setup(monkeypatch, process_running=True)
    archived, archive = _archiver()
    active = [_row("claude:old", "/dev/ttys004", 100.0), _row("claude:new", "/dev/ttys004", 200.0)]
    order = (100, 10, 1)

    watcher._archive_stale_sessions(
        active,
        archive,
        {},
        _pane_locations(active, alive=True, order=order),
        session_orders={"claude:old": order, "claude:new": order},
    )

    assert archived == []


def test_missing_channel_identity_is_not_inferred_from_another_rows_tty(monkeypatch):
    _setup(monkeypatch, process_running=True)
    archived, archive = _archiver()
    active = [_row("claude:old", "/dev/ttys004", 100.0), _row("claude:new", "/dev/ttys004", 200.0)]
    order = (200, 10, 2)

    watcher._archive_stale_sessions(
        active,
        archive,
        {},
        _pane_locations(active, alive=True, order=order),
        session_orders={"claude:new": order},
    )

    assert archived == []


def test_both_go_when_the_process_is_gone(monkeypatch):
    """The shell is idle, so neither session is running on it any more."""
    _setup(monkeypatch, process_running=False)
    archived, archive = _archiver()
    active = [_row("claude:old", "/dev/ttys004", 100.0), _row("claude:new", "/dev/ttys004", 200.0)]

    watcher._archive_stale_sessions(
        active,
        archive,
        {},
        _pane_locations(active, alive=True),
    )

    assert sorted(archived) == ["claude:new", "claude:old"]


def test_codex_running_as_node_is_detected(monkeypatch):
    class Result:
        returncode = 0
        stderr = ""
        stdout = "node /opt/codex/bin/codex --some-flag\n"

    monkeypatch.setattr(watcher.subprocess, "run", lambda *args, **kwargs: Result())

    assert watcher.process_on_tty("/dev/ttys004", "codex") is True


def test_harness_name_in_an_argument_path_is_not_a_process_match(monkeypatch):
    class Result:
        returncode = 0
        stderr = ""
        stdout = "vim /Users/peter/play/codex-notes/todo.md\n"

    monkeypatch.setattr(watcher.subprocess, "run", lambda *args, **kwargs: Result())

    assert watcher.process_on_tty("/dev/ttys004", "codex") is False


def test_a_dead_pane_is_archived_before_any_grouping(monkeypatch):
    _setup(monkeypatch, process_running=True)
    archived, archive = _archiver()
    active = [_row("claude:gone", "/dev/ttys004", 100.0)]

    watcher._archive_stale_sessions(
        active,
        archive,
        {},
        _pane_locations(active, alive=False),
    )

    assert archived == ["claude:gone"]


def test_different_ttys_do_not_compete(monkeypatch):
    """Two live sessions in different shells are both current."""
    _setup(monkeypatch, process_running=True)
    archived, archive = _archiver()
    active = [_row("claude:a", "/dev/ttys004", 100.0), _row("claude:b", "/dev/ttys005", 200.0)]

    watcher._archive_stale_sessions(
        active,
        archive,
        {},
        _pane_locations(active, alive=True),
    )

    assert archived == []


def test_a_row_without_a_tty_is_left_alone(monkeypatch):
    """Nothing here can decide anything about it - and it must not take another down."""
    _setup(monkeypatch, process_running=True)
    archived, archive = _archiver()
    active = [_row("claude:no-tty", None, 100.0), _row("claude:live", "/dev/ttys004", 200.0)]

    watcher._archive_stale_sessions(
        active,
        archive,
        {},
        _pane_locations(active, alive=True),
    )

    assert archived == []
