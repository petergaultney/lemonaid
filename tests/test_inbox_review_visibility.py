"""Reviewers stay quiet until their row is chosen or their brief needs attention."""

import asyncio
import itertools
import time
from pathlib import Path

import pytest
from textual.coordinate import Coordinate
from textual.widgets import DataTable

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.config import load_config
from lemonaid.inbox import db, pins, presence, view
from lemonaid.inbox.arrange.cli import _snapshot
from lemonaid.inbox.tui import app as app_mod
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.brief_cards import BriefCache
from lemonaid.inbox.tui.utils import HERE_BLOCK

_ids = itertools.count(1)


def _session(conn, name: str, *, unread: bool = False, tty: str = "", source: str = "tmux") -> str:
    channel = f"claude:{name}"
    row = db.add(
        conn,
        channel,
        "a message",
        name,
        {"tty": tty or f"/dev/ttys{next(_ids)}", "cwd": "/tmp", "session_id": name},
    )
    conn.execute(
        "UPDATE notifications SET switch_source = ?, status = ? WHERE id = ?",
        (source, "unread" if unread else "read", row.id),
    )
    conn.commit()
    return channel


def _brief(conn, channel: str, status: str, *, reviewer: bool = False) -> Path:
    stem = f"review-{channel.split(':')[1]}" if reviewer else f"work-{channel.split(':')[1]}"
    path = brief_store.briefs_dir() / f"2026-10-07-{stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    title = "Review a PR" if reviewer else "Work on a PR"
    path.write_text(f"# {title}\n\nBrief-ID: {stem}.SampleBin\n\nStatus: {status}\n\n## Now\n")
    identity.ensure(conn, path)
    attached.attach(conn, channel, path)
    return path


@pytest.fixture(autouse=True)
def _keep_sessions(monkeypatch):
    monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)


def _run(steps, size=(120, 40)):
    async def run():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def _channels(table: DataTable) -> list[str]:
    with db.connect() as conn:
        return [
            db.get(conn, int(table.coordinate_to_cell_key(Coordinate(i, 0))[0].value)).channel
            for i in range(table.row_count)
        ]


def test_quiet_reviewers_hide_even_when_unread_and_a_renamed_reviewer_stays_identified():
    with db.connect() as conn:
        reviewer = _session(conn, "reviewer", unread=True)
        ordinary = _session(conn, "worker")
        _brief(conn, reviewer, "waiting", reviewer=True)
        _brief(conn, ordinary, "waiting")
        db.update_name(
            conn, db.get_by_channel(conn, reviewer, unread_only=False).id, "ordinary name"
        )
        active = view.ordered_active(
            conn, "tmux", BriefCache(), presence.Probe(), False, time.time()
        )

    assert active.reviewers == {reviewer}
    assert [row.channel for row in view.inbox_rows(active, set(), set())] == [ordinary]


@pytest.mark.parametrize(
    "status", ["alert", "blocked", "running", "merge", "approve", "review", "done"]
)
def test_every_special_brief_status_keeps_a_reviewer_visible(status):
    with db.connect() as conn:
        reviewer = _session(conn, "reviewer")
        _brief(conn, reviewer, status, reviewer=True)
        active = view.ordered_active(
            conn, "tmux", BriefCache(), presence.Probe(), False, time.time()
        )

    assert [row.channel for row in view.inbox_rows(active, set(), set())] == [reviewer]


def test_pin_keeps_a_quiet_reviewer_visible():
    with db.connect() as conn:
        reviewer = _session(conn, "reviewer")
        _brief(conn, reviewer, "waiting", reviewer=True)
        pins.pin(conn, reviewer)
        active = view.ordered_active(
            conn, "tmux", BriefCache(), presence.Probe(), False, time.time()
        )

    assert [row.channel for row in view.inbox_rows(active, {reviewer}, set())] == [reviewer]


def test_arranger_snapshot_uses_the_same_default_visibility():
    with db.connect() as conn:
        reviewer = _session(conn, "reviewer")
        ordinary = _session(conn, "worker")
        _brief(conn, reviewer, "waiting", reviewer=True)

    snapshot, shown, folded = _snapshot(load_config(), "table", 120)

    assert [row.channel for row in shown] == [ordinary]
    assert folded == []
    assert [row["channel"] for row in snapshot["rows"]] == [ordinary]


@pytest.mark.parametrize("size", [(120, 40), (40, 60)])
def test_switching_to_a_reviewer_shows_it_in_both_inbox_layouts(monkeypatch, size):
    focused = set()
    monkeypatch.setattr(app_mod.navigation, "focused_ttys", lambda socket=None: focused)
    monkeypatch.setattr(app_mod, "_FOCUS_CACHE_SECONDS", 0.0)
    with db.connect() as conn:
        reviewer = _session(conn, "reviewer", tty="/dev/ttys-reviewer")
        ordinary = _session(conn, "worker")
        _brief(conn, reviewer, "waiting", reviewer=True)

    async def steps(app, pilot):
        before = app._row_channels()
        focused.add("/dev/ttys-reviewer")
        app._refresh_notifications()
        await pilot.pause()
        shown = app._row_channels()
        focused.clear()
        app._select_channel(ordinary)
        app._refresh_notifications()
        await pilot.pause()
        return before, shown, app._row_channels()

    before, shown, after = _run(steps, size)
    assert before == after == [ordinary]
    assert set(shown) == {reviewer, ordinary}


def test_selected_reviewer_stays_until_the_cursor_moves():
    with db.connect() as conn:
        reviewer = _session(conn, "reviewer")
        ordinary = _session(conn, "worker")
        path = _brief(conn, reviewer, "blocked", reviewer=True)

    async def steps(app, pilot):
        app._select_channel(reviewer)
        path.write_text(path.read_text().replace("Status: blocked", "Status: waiting"))
        app._refresh_notifications()
        await pilot.pause()
        held = app._row_channels()
        selected = held[app.query_one("#main_table", DataTable).cursor_row]
        app._select_channel(ordinary)
        app._refresh_notifications()
        await pilot.pause()
        return held, selected, app._row_channels()

    held, selected, after = _run(steps)
    assert set(held) == {reviewer, ordinary}
    assert selected == reviewer
    assert after == [ordinary]


def test_reviewer_stays_visible_with_here_bar_when_inbox_cursor_moves(monkeypatch):
    monkeypatch.setattr(
        app_mod.navigation, "focused_ttys", lambda socket=None: {"/dev/ttys-reviewer"}
    )
    monkeypatch.setattr(app_mod, "_FOCUS_CACHE_SECONDS", 0.0)
    with db.connect() as conn:
        reviewer = _session(conn, "reviewer", tty="/dev/ttys-reviewer")
        ordinary = _session(conn, "worker")
        _brief(conn, reviewer, "waiting", reviewer=True)

    async def steps(app, pilot):
        app._select_channel(ordinary)
        app._refresh_notifications()
        await pilot.pause()
        rows = app._row_channels()
        table = app.query_one("#main_table", DataTable)
        reviewer_cell = table.get_cell_at(Coordinate(rows.index(reviewer), 3))
        return rows, reviewer_cell.plain, rows[table.cursor_row]

    rows, name_cell, selected = _run(steps)
    assert set(rows) == {reviewer, ordinary}
    assert selected == ordinary
    assert HERE_BLOCK in name_cell


def test_selected_reviewer_in_lower_table_stays_selected_when_status_turns_quiet():
    with db.connect() as conn:
        _session(conn, "main")
        reviewer = _session(conn, "reviewer", source="wezterm")
        ordinary = _session(conn, "other", source="wezterm")
        path = _brief(conn, reviewer, "blocked", reviewer=True)

    async def steps(app, pilot):
        table = app.query_one("#other_sources_table", DataTable)
        assert _channels(table) == [reviewer, ordinary]
        table.focus()
        table.move_cursor(row=0)
        await pilot.pause()
        path.write_text(path.read_text().replace("Status: blocked", "Status: waiting"))
        app._refresh_notifications()
        await pilot.pause()
        held = _channels(table)
        selected = held[table.cursor_row]
        table.move_cursor(row=held.index(ordinary))
        app._refresh_notifications()
        await pilot.pause()
        return held, selected, _channels(table)

    held, selected, after = _run(steps)
    assert set(held) == {reviewer, ordinary}
    assert selected == reviewer
    assert after == [ordinary]
