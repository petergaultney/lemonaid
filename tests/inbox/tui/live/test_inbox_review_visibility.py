"""Reviewers stay quiet until their row is chosen or their brief needs attention."""

import asyncio
import itertools
import os
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
from lemonaid.inbox.tui.rows.brief_cards import BriefCache
from lemonaid.inbox.tui.utils import HERE_BLOCK
from lemonaid.inbox.tui.watchers import focus, watcher_hooks
from lemonaid.lineage import links as lineage_links

_ids = itertools.count(1)
_PR_URL = "https://github.com/petergaultney/lemonaid/pull/267"


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


def _parent_brief(conn, lemon_id: str, pr_url: str | None = None) -> Path:
    path = brief_store.briefs_dir() / f"2026-10-07-parent-{lemon_id.split('.')[0]}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"# Parent work\n\nBrief-ID: {lemon_id}\n"
    if pr_url:
        content += (
            "\n## Now\n\n### PRs\n\n| Work | PR | Review |\n|---|---|---|\n"
            f"| Work | [PR]({pr_url}) | |\n"
        )
    path.write_text(content)
    identity.ensure(conn, path)
    return path


def _brief(
    conn,
    channel: str,
    status: str,
    *,
    reviewer: bool = False,
    parent: str | None = "author.WorkerBin",
    hidden: bool = True,
) -> Path:
    stem = f"review-{channel.split(':')[1]}" if reviewer else f"work-{channel.split(':')[1]}"
    path = brief_store.briefs_dir() / f"2026-10-07-{stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    title = "Review a PR" if reviewer else "Work on a PR"
    if not reviewer:
        parent = None
    elif parent == "author.WorkerBin":
        _parent_brief(conn, parent, _PR_URL)
    parent_line = f"Parent: {parent}, 2026-10-13\n\n" if parent else ""
    parent_line += "Hidden: yes\n\n" if reviewer and hidden else ""
    path.write_text(
        f"# {title}\n\nBrief-ID: {stem}.SampleBin\n\n{parent_line}"
        f"Status: {status}\n\n## Goal\nReview {_PR_URL if reviewer else 'work'}.\n\n## Now\n"
    )
    identity.ensure(conn, path)
    attached.attach(conn, channel, path)
    if parent and identity.valid(parent):
        lineage_links.set_parent(conn, identity.read(path.read_text()), parent)
    return path


@pytest.fixture(autouse=True)
def _keep_sessions(monkeypatch):
    monkeypatch.setattr(watcher_hooks, "archive_channel", lambda channel: None)


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
    ("kind", "unread", "moved_on", "shown"),
    [
        ("permission_prompt", True, False, True),
        ("PermissionRequest", True, False, True),
        ("permission_prompt", False, False, True),  # read, but nobody answered it
        ("permission_prompt", False, True, False),
        ("Stop", True, False, False),
    ],
)
def test_a_reviewer_stuck_on_a_prompt_stays_visible(kind, unread, moved_on, shown):
    with db.connect() as conn:
        reviewer = _session(conn, "reviewer", unread=unread)
        row = db.get_by_channel(conn, reviewer, unread_only=False)
        row = db.add(
            conn,
            reviewer,
            "Running kubectl",
            "reviewer",
            {**row.metadata, "notification_type": kind},
            status="unread" if unread else "read",
            switch_source="tmux",
        )
        db.record_turn(conn, reviewer, row.created_at + (5 if moved_on else -1))
        _brief(conn, reviewer, "", reviewer=True)
        active = view.ordered_active(
            conn, "tmux", BriefCache(), presence.Probe(), False, time.time()
        )

    assert [row.channel for row in view.inbox_rows(active, set(), set())] == (
        [reviewer] if shown else []
    )


def test_a_reviewer_without_the_hidden_line_stays_visible():
    with db.connect() as conn:
        reviewer = _session(conn, "reviewer")
        _brief(conn, reviewer, "waiting", reviewer=True, hidden=False)
        active = view.ordered_active(
            conn, "tmux", BriefCache(), presence.Probe(), False, time.time()
        )

    assert active.reviewers == set()
    assert [row.channel for row in view.inbox_rows(active, set(), set())] == [reviewer]


def test_any_quiet_lemon_with_the_hidden_line_hides_whatever_its_parent():
    with db.connect() as conn:
        reviewer = _session(conn, "reviewer")
        _brief(conn, reviewer, "waiting", reviewer=True, parent="someone.AnyBin")
        active = view.ordered_active(
            conn, "tmux", BriefCache(), presence.Probe(), False, time.time()
        )

    assert active.reviewers == {reviewer}
    assert view.inbox_rows(active, set(), set()) == []


def test_keep_hidden_returns_hidden_lemons_for_the_fold():
    with db.connect() as conn:
        reviewer = _session(conn, "reviewer")
        _brief(conn, reviewer, "waiting", reviewer=True)
        active = view.ordered_active(
            conn, "tmux", BriefCache(), presence.Probe(), False, time.time()
        )

    assert view.inbox_rows(active, set(), set()) == []
    assert [r.channel for r in view.inbox_rows(active, set(), set(), True)] == [reviewer]
    assert view.hidden_channels(active, set(), set()) == {reviewer}


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

    snapshot, shown, folded, hidden = _snapshot(load_config(), "table", 120)

    assert [row.channel for row in shown] == [ordinary]
    assert folded == []
    assert hidden == frozenset()
    assert [row["channel"] for row in snapshot["rows"]] == [ordinary]


@pytest.mark.parametrize("unread", [False, True])
def test_arranger_snapshot_folds_hidden_lemons_as_the_inbox_does(unread):
    Path(os.environ["LEMONAID_CONFIG"]).write_text('[tui]\nfold_statuses = ["idle"]\n')
    with db.connect() as conn:
        reviewer = _session(conn, "reviewer", unread=unread)
        ordinary = _session(conn, "worker")
        _brief(conn, reviewer, "waiting", reviewer=True)

    snapshot, shown, folded, hidden = _snapshot(load_config(), "table", 120)

    assert [row.channel for row in shown] == [ordinary]
    assert [row.channel for row in folded] == [reviewer]
    assert hidden == {reviewer}
    assert [row["channel"] for row in snapshot["rows"]] == [ordinary, reviewer]


@pytest.mark.parametrize("size", [(120, 40), (40, 60)])
def test_switching_to_a_reviewer_shows_it_in_both_inbox_layouts(monkeypatch, size):
    focused = set()
    monkeypatch.setattr(app_mod.navigation, "focused_ttys", lambda socket=None: focused)
    monkeypatch.setattr(focus, "FOCUS_CACHE_SECONDS", 0.0)
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
    monkeypatch.setattr(focus, "FOCUS_CACHE_SECONDS", 0.0)
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


def test_search_keeps_a_deaf_lemon_in_the_lower_table(monkeypatch):
    monkeypatch.setattr(
        presence.Probe, "marks", lambda self, rows, lemon_ids, now: {"claude:deaf": "deaf"}
    )
    with db.connect() as conn:
        _session(conn, "main")
        deaf = _session(conn, "deaf", source="wezterm")
        other = _session(conn, "other", source="wezterm")
        _brief(conn, deaf, "waiting")

    async def steps(app, pilot):
        app._content.searching = True
        app._content.filter_text = "no-such-text"
        app._refresh_notifications()
        await pilot.pause()
        return _channels(app.query_one("#other_sources_table", DataTable))

    assert other not in (rows := _run(steps))
    assert rows == [deaf]
