"""Below the pins: blocked, then unread, then read done, then everything else read."""

import asyncio
import itertools
import time

import pytest
from textual.widgets import DataTable

from lemonaid.brief import attached
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db, order, pins
from lemonaid.inbox.tui.app import LemonaidApp

_ids = itertools.count(900)


def _session(conn, name: str, *, unread: bool = False, age: float = 0) -> str:
    """A live tmux session in the main table, read unless `unread`."""
    channel = f"claude:{name}"
    n = db.add(
        conn,
        channel,
        "a message",
        name,
        {"tty": f"/dev/ttys{next(_ids)}", "cwd": "/tmp", "session_id": f"s{next(_ids)}"},
    )
    conn.execute(
        "UPDATE notifications SET switch_source = 'tmux', status = ?, created_at = ? WHERE id = ?",
        ("unread" if unread else "read", time.time() - age, n.id),
    )
    conn.commit()
    return channel


def _brief(conn, channel: str, status: str) -> None:
    path = brief_store.briefs_dir() / f"{channel.replace(':', '-')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# work\n\nStatus: {status}\n\n## Now\n")
    attached.attach(conn, channel, path)


@pytest.fixture(autouse=True)
def _keep_sessions(monkeypatch):
    """The test tmux has none of these ttys, so the watcher would archive every row."""
    monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)


def _run(steps, size):
    async def run():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def _drawn(size) -> list[str]:
    async def steps(app, pilot):
        return app._row_channels()

    return _run(steps, size)


def _sorted(rows: list[tuple[str, str, bool]]) -> list[str]:
    notifications = [
        db.Notification(i, channel, "", status="unread" if unread else "read")
        for i, (channel, _status, unread) in enumerate(rows)
    ]
    statuses = {channel: status for channel, status, _unread in rows}
    return [n.channel for n in order.by_status(notifications, statuses, set())]


def test_a_read_blocked_session_sorts_above_an_unread_one():
    assert _sorted([("c:fresh", "working", True), ("c:blocked", "blocked", False)]) == [
        "c:blocked",
        "c:fresh",
    ]


def test_unread_sorts_above_every_read_status_but_blocked():
    rows = [
        ("c:waiting", "waiting", False),
        ("c:done", "done", False),
        ("c:plain", "", False),
        ("c:unread-waiting", "waiting", True),
        ("c:unread-done", "done", True),
    ]

    assert _sorted(rows) == [
        "c:unread-waiting",
        "c:unread-done",
        "c:done",
        "c:waiting",
        "c:plain",
    ]


def test_read_working_waiting_and_no_brief_share_a_band():
    rows = [("c:none", "", False), ("c:working", "working", False), ("c:waiting", "waiting", False)]

    assert _sorted(rows) == ["c:none", "c:working", "c:waiting"]


def test_pins_come_first_then_bands_then_unread_then_recency():
    with db.connect() as conn:
        old_unread = _session(conn, "old-unread", unread=True, age=300)
        new_read = _session(conn, "new-read", age=10)
        pinned = _session(conn, "pinned", age=500)
        blocked = _session(conn, "blocked", age=900)
        pins.pin(conn, pinned)
        _brief(conn, blocked, "blocked")

    assert _drawn((120, 40)) == [pinned, blocked, old_unread, new_read]


def test_a_done_pin_stays_above_a_blocked_session():
    with db.connect() as conn:
        pinned = _session(conn, "pinned")
        blocked = _session(conn, "blocked")
        pins.pin(conn, pinned)
        _brief(conn, pinned, "done")
        _brief(conn, blocked, "blocked")

    assert _drawn((120, 40)) == [pinned, blocked]


def test_the_sidebar_and_the_wide_inbox_agree():
    with db.connect() as conn:
        channels = [
            _session(conn, name, unread=unread, age=age)
            for name, unread, age in [
                ("a", True, 50),
                ("b", False, 40),
                ("c", True, 30),
                ("d", False, 20),
                ("e", False, 10),
            ]
        ]
        _brief(conn, channels[0], "done")
        _brief(conn, channels[1], "blocked")
        _brief(conn, channels[2], "waiting")
        pins.pin(conn, channels[4])

    wide = _drawn((120, 40))

    assert wide == _drawn((40, 60))
    assert wide == [channels[4], channels[1], channels[2], channels[0], channels[3]]


def test_a_pin_trades_places_with_a_pin_of_another_status():
    with db.connect() as conn:
        blocked = _session(conn, "blocked")
        working = _session(conn, "working")
        pins.pin(conn, blocked)
        pins.pin(conn, working)
        _brief(conn, blocked, "blocked")

    async def steps(app, pilot):
        app._select_channel(working)
        app.action_move_pin_up()
        await pilot.pause()
        return app._row_channels()

    assert _run(steps, (120, 40)) == [working, blocked]


def test_jumping_to_unread_finds_the_oldest_in_any_band(monkeypatch):
    with db.connect() as conn:
        _session(conn, "blocked-read", age=5)
        oldest = _session(conn, "oldest", unread=True, age=600)
        _session(conn, "newer", unread=True, age=60)
        _brief(conn, "claude:blocked-read", "blocked")
        _brief(conn, oldest, "done")

    selected = []
    monkeypatch.setattr(
        DataTable, "action_select_cursor", lambda table: selected.append(table.cursor_row)
    )

    async def steps(app, pilot):
        app.action_jump_unread()
        return app._row_channels()

    drawn = _run(steps, (120, 40))

    assert drawn[-1] == oldest
    assert selected == [len(drawn) - 1]


def test_marking_a_blocked_row_read_moves_to_the_unread_below_it():
    """The blocked row stays on top once read, so the cursor must skip past it."""
    with db.connect() as conn:
        blocked = _session(conn, "blocked", unread=True, age=5)
        other = _session(conn, "other", unread=True, age=60)
        _session(conn, "read", age=10)
        _brief(conn, blocked, "blocked")

    async def steps(app, pilot):
        app._select_channel(blocked)
        app.action_mark_read()
        await pilot.pause()
        return app._row_channels()[app.query_one("#main_table", DataTable).cursor_row]

    assert _run(steps, (120, 40)) == other
