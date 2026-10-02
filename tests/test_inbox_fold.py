"""Sessions whose brief status is in `[tui] fold_statuses` fold into one line at the list's bottom."""

import asyncio
import itertools
import os
import time
from pathlib import Path

import pytest
from textual.widgets import DataTable, Static

from lemonaid.brief import attached
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db, order, pins
from lemonaid.inbox.tui import app as app_mod
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.help_screen import help_lines

_ids = itertools.count(700)


def _session(conn, name: str, *, unread: bool = False, age: float = 0, tty: str = "") -> str:
    channel = f"claude:{name}"
    n = db.add(
        conn,
        channel,
        "a message",
        name,
        {"tty": tty or f"/dev/ttys{next(_ids)}", "cwd": "/tmp", "session_id": f"s{next(_ids)}"},
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


@pytest.fixture
def fold_waiting():
    Path(os.environ["LEMONAID_CONFIG"]).write_text('[tui]\nfold_statuses = ["waiting"]\n')


def _run(steps, size=(120, 40)):
    async def run():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def _label(app) -> str:
    label = app.query_one("#fold_label", Static)
    return str(label.render()) if label.display else ""


def _drawn_and_label(size=(120, 40)) -> tuple[list[str], str]:
    async def steps(app, pilot):
        return app._row_channels(), _label(app)

    return _run(steps, size)


def _split(
    rows: list[tuple[str, str, bool]], pinned=frozenset(), in_view=frozenset()
) -> tuple[list[str], list[str]]:
    notifications = [
        db.Notification(i, channel, "", status="unread" if unread else "read")
        for i, (channel, _status, unread) in enumerate(rows)
    ]
    statuses = {channel: status for channel, status, _unread in rows}
    shown, folded = order.fold(notifications, statuses, pinned, {"waiting"}, in_view)
    return [n.channel for n in shown], [n.channel for n in folded]


def test_read_rows_of_a_folded_status_fold_and_keep_their_order():
    rows = [
        ("c:w1", "waiting", False),
        ("c:working", "working", False),
        ("c:w2", "waiting", False),
        ("c:none", "", False),
    ]

    assert _split(rows) == (["c:working", "c:none"], ["c:w1", "c:w2"])


def test_unread_and_pinned_rows_never_fold():
    rows = [("c:unread", "waiting", True), ("c:pinned", "waiting", False)]

    assert _split(rows, pinned={"c:pinned"}) == (["c:unread", "c:pinned"], [])


def test_a_row_in_view_never_folds():
    rows = [("c:focused", "waiting", False), ("c:other", "waiting", False)]

    assert _split(rows, in_view={"c:focused"}) == (["c:focused"], ["c:other"])


def test_nothing_folds_without_the_setting():
    with db.connect() as conn:
        waiting = _session(conn, "waiting")
        _brief(conn, waiting, "waiting")

    assert _drawn_and_label() == ([waiting], "")


def test_folded_rows_leave_the_list_and_the_label_counts_them(fold_waiting):
    with db.connect() as conn:
        working = _session(conn, "working", age=30)
        w1 = _session(conn, "w1", age=20)
        w2 = _session(conn, "w2", age=10)
        _brief(conn, working, "working")
        _brief(conn, w1, "waiting")
        _brief(conn, w2, "waiting")

    drawn, label = _drawn_and_label()

    assert drawn == [working]
    assert label == "▸ waiting (2) · w to show"


def test_the_fold_key_opens_the_group_at_the_bottom_and_closes_it(fold_waiting):
    with db.connect() as conn:
        waiting = _session(conn, "waiting", age=5)
        working = _session(conn, "working", age=30)
        _brief(conn, waiting, "waiting")

    async def steps(app, pilot):
        await pilot.press("w")
        await pilot.pause()
        opened = app._row_channels(), _label(app)
        await pilot.press("w")
        await pilot.pause()
        return opened, (app._row_channels(), _label(app))

    opened, closed = _run(steps)

    assert opened == ([working, waiting], "▴ waiting (1) above · w to fold")
    assert closed == ([working], "▸ waiting (1) · w to show")


def test_an_unread_waiting_row_breaks_out_and_a_pinned_one_stays(fold_waiting):
    with db.connect() as conn:
        unread = _session(conn, "unread", unread=True)
        pinned = _session(conn, "pinned")
        folded = _session(conn, "folded")
        for channel in (unread, pinned, folded):
            _brief(conn, channel, "waiting")
        pins.pin(conn, pinned)

    drawn, label = _drawn_and_label()

    assert drawn == [pinned, unread]
    assert label == "▸ waiting (1) · w to show"


def test_the_sidebar_folds_the_same_rows(fold_waiting):
    with db.connect() as conn:
        working = _session(conn, "working")
        waiting = _session(conn, "waiting")
        _brief(conn, waiting, "waiting")

    assert _drawn_and_label((40, 60)) == ([working], "▸ waiting (1) · w to show")


def _help_lists_fold(app) -> bool:
    return any(
        "folded sessions" in desc
        for _t, rows in help_lines(app.screen.keybindings)
        for _k, desc in rows
    )


def test_the_key_reference_lists_the_fold_key_only_when_something_folds(fold_waiting):
    async def steps(app, pilot):
        await pilot.press("question_mark")
        await pilot.pause()
        return _help_lists_fold(app)

    assert _run(steps)
    Path(os.environ["LEMONAID_CONFIG"]).write_text("")
    assert not _run(steps)


def _selected(app) -> str:
    return app._row_channels()[app.query_one("#main_table", DataTable).cursor_row]


def test_closing_the_group_on_a_folded_row_selects_the_last_row_left(fold_waiting):
    with db.connect() as conn:
        waiting = _session(conn, "waiting", age=5)
        working = _session(conn, "working", age=30)
        _brief(conn, waiting, "waiting")

    async def steps(app, pilot):
        await pilot.press("w")
        await pilot.pause()
        app._select_channel(waiting)
        await pilot.press("w")
        await pilot.pause()
        return _selected(app)

    assert _run(steps) == working


def test_a_selected_folded_row_that_turns_unread_stays_selected(fold_waiting):
    with db.connect() as conn:
        waiting = _session(conn, "waiting", age=5)
        _session(conn, "working", age=30)
        _brief(conn, waiting, "waiting")

    async def steps(app, pilot):
        await pilot.press("w")
        await pilot.pause()
        app._select_channel(waiting)
        app.action_mark_unread()
        await pilot.pause()
        return _selected(app), _label(app)

    assert _run(steps) == (waiting, "")


@pytest.fixture
def focus(monkeypatch) -> dict[str, set[str]]:
    """The ttys tmux reports as focused, asked afresh on every refresh."""
    focused: dict[str, set[str]] = {"ttys": set()}
    monkeypatch.setattr(app_mod.navigation, "focused_ttys", lambda socket=None: focused["ttys"])
    monkeypatch.setattr(app_mod, "_FOCUS_CACHE_SECONDS", 0.0)
    return focused


def test_a_focused_waiting_lemon_leaves_the_fold_and_returns_when_focus_moves(fold_waiting, focus):
    with db.connect() as conn:
        working = _session(conn, "working", age=30)
        waiting = _session(conn, "waiting", age=5, tty="/dev/ttys-focus")
        _brief(conn, waiting, "waiting")

    async def steps(app, pilot):
        app._select_channel(working)
        focus["ttys"] = {"/dev/ttys-focus"}
        app._refresh_notifications()
        await pilot.pause()
        focused = app._row_channels(), _label(app)
        focus["ttys"] = set()
        app._refresh_notifications()
        await pilot.pause()
        return focused, (app._row_channels(), _label(app))

    focused, left = _run(steps)

    assert focused == ([waiting, working], "")
    assert left == ([working], "▸ waiting (1) · w to show")


def test_a_lemon_that_loses_focus_under_the_cursor_stays_until_the_cursor_moves(
    fold_waiting, focus
):
    with db.connect() as conn:
        working = _session(conn, "working", age=30)
        waiting = _session(conn, "waiting", age=5, tty="/dev/ttys-focus")
        _brief(conn, waiting, "waiting")

    async def steps(app, pilot):
        focus["ttys"] = {"/dev/ttys-focus"}
        app._refresh_notifications()
        await pilot.pause()
        app._select_channel(waiting)
        focus["ttys"] = set()
        app._refresh_notifications()
        await pilot.pause()
        held = app._row_channels(), _selected(app)
        app._select_channel(working)
        app._refresh_notifications()
        await pilot.pause()
        return held, app._row_channels()

    held, moved = _run(steps)

    assert held == ([waiting, working], waiting)
    assert moved == [working]
