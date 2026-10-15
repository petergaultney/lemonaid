"""The hide key edits temporary briefs and refreshes both inbox layouts."""

import asyncio

import pytest
from textual.widgets import DataTable

from lemonaid.brief import attached, hidden, identity, store, verbs_cli
from lemonaid.inbox import db, pins
from lemonaid.inbox.tui import app as app_mod
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.watchers import watcher_hooks


def _session(name, *, status="", source="tmux", has_brief=True):
    with db.connect() as conn:
        row = db.add(conn, f"claude:{name}", "message", name, {"cwd": "/tmp"})
        conn.execute(
            "UPDATE notifications SET switch_source = ?, status = 'read' WHERE id = ?",
            (source, row.id),
        )
        conn.commit()
        if not has_brief:
            return row, None

        path = store.briefs_dir() / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# {name}\n\nBrief-ID: {name}.SampleBin\n\n"
            + (f"Status: {status}\n\n" if status else "")
            + "## Goal\n\nWork.\n"
        )
        identity.ensure(conn, path)
        attached.attach(conn, row.channel, path)
        return row, path


@pytest.fixture(autouse=True)
def _keep_sessions(monkeypatch):
    monkeypatch.setattr(watcher_hooks, "archive_channel", lambda channel: None)


def _run(steps, size=(120, 20)):
    async def run():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await steps(app, pilot)

    asyncio.run(run())


@pytest.mark.parametrize("size", [(120, 20), (40, 30)])
@pytest.mark.parametrize("count,index", [(1, 0), (3, 1), (3, 2), (30, 20)])
def test_hide_removes_row_and_keeps_neighbor_and_scroll(size, count, index):
    sessions = [_session(f"worker{i}") for i in range(count)]
    row, path = sessions[index]

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        app._select_channel(row.channel)
        await pilot.pause()
        before = table.scroll_y
        order = app._row_channels()
        position = order.index(row.channel)
        await pilot.press("H")
        await pilot.pause()
        assert hidden.is_hidden(path.read_text())
        remaining = [channel for channel in order if channel != row.channel]
        assert app._row_channels() == remaining
        if remaining:
            assert app._selected_channel() == remaining[min(position, len(remaining) - 1)]
            assert table.scroll_y == min(before, table.max_scroll_y)
        app._refresh_notifications()
        assert row.channel not in app._row_channels()

    _run(steps, size)


def test_search_finds_hidden_lemon_and_key_unhides_it():
    row, path = _session("quiet")
    store.edit(path, lambda text: hidden.with_hidden(text, True))
    _session("visible")

    async def steps(app, pilot):
        assert row.channel not in app._row_channels()
        await pilot.press("/", "q", "u", "i", "e", "t", "down")
        await pilot.pause()
        assert app._row_channels() == [row.channel]
        await pilot.press("H")
        assert not hidden.is_hidden(path.read_text())
        app._stop_search()
        await pilot.pause()
        assert row.channel in app._row_channels()

    _run(steps)


@pytest.mark.parametrize("status,pinned", [("blocked", False), ("review", False), ("", True)])
def test_hide_keeps_visibility_exceptions(status, pinned):
    row, path = _session("worker", status=status)
    if pinned:
        with db.connect() as conn:
            pins.toggle(conn, row.channel)

    async def steps(app, pilot):
        await pilot.press("H")
        assert hidden.is_hidden(path.read_text())
        assert row.channel in app._row_channels()
        await pilot.press("H")
        assert not hidden.is_hidden(path.read_text())

    _run(steps)


def test_no_brief_leaves_the_row_visible(monkeypatch):
    row, _ = _session("bare", has_brief=False)
    notices = []

    async def steps(app, pilot):
        monkeypatch.setattr(app, "notify", lambda message, **kwargs: notices.append(message))
        await pilot.press("H")
        assert row.channel in app._row_channels()
        assert "No attached brief" in notices[-1]

    _run(steps)


def test_checked_writer_failure_is_reported(monkeypatch):
    row, path = _session("worker")
    monkeypatch.setattr(verbs_cli, "edit", lambda *args: "Refused edit")
    notices = []

    async def steps(app, pilot):
        monkeypatch.setattr(app, "notify", lambda message, **kwargs: notices.append(message))
        await pilot.press("H")
        assert row.channel in app._row_channels()
        assert not hidden.is_hidden(path.read_text())
        assert notices[-1] == "Refused edit"

    _run(steps)


def test_hide_in_other_terminal_table():
    _session("main")
    row, path = _session("other", source="wezterm")

    async def steps(app, pilot):
        table = app.query_one("#other_sources_table", DataTable)
        table.focus()
        await pilot.press("H")
        assert hidden.is_hidden(path.read_text())
        assert table.row_count == 0
        assert app.focused is app.query_one("#main_table", DataTable)

    _run(steps)


def test_hide_keeps_focused_lemon_visible(monkeypatch):
    row, path = _session("focused")
    with db.connect() as conn:
        conn.execute(
            "UPDATE notifications SET metadata = ? WHERE id = ?",
            ('{"tty": "/dev/test-focused", "cwd": "/tmp"}', row.id),
        )
        conn.commit()
    monkeypatch.setattr(
        app_mod.navigation, "focused_ttys", lambda socket=None: {"/dev/test-focused"}
    )

    async def steps(app, pilot):
        await pilot.press("H")
        assert hidden.is_hidden(path.read_text())
        assert row.channel in app._row_channels()

    _run(steps)


def test_ctrl_s_saves_pane_size_without_hiding(monkeypatch):
    row, path = _session("worker")
    saved = []
    monkeypatch.setattr(app_mod, "current_position", lambda fallback: "left")
    monkeypatch.setattr(app_mod, "save_current_size", saved.append)

    async def steps(app, pilot):
        app._scratch_mode = True
        await pilot.press("ctrl+s")
        assert saved == ["left"]
        assert not hidden.is_hidden(path.read_text())
        assert row.channel in app._row_channels()
        await pilot.press("H")
        assert saved == ["left"]
        assert hidden.is_hidden(path.read_text())

    _run(steps)
