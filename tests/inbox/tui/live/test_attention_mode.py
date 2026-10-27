"""Attention mode: `!` folds every lemon that doesn't need you, and remembers the choice."""

import asyncio
import itertools
import json
import os
import threading
import time
from pathlib import Path

import pytest
from textual.widgets import Static

from lemonaid import groups
from lemonaid.brief import attached
from lemonaid.brief import store as brief_store
from lemonaid.grove.source import inbox_keys
from lemonaid.inbox import attention, db, order, sections
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.live import attention_summary, group_headers
from lemonaid.inbox.tui.watchers import watcher_hooks

_ids = itertools.count(900)
_RULE = order.attention_rule(["alert", "blocked", "merge", "approve", "running"])


def _session(conn, name: str, *, unread: bool = False, age: float = 0) -> str:
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
    monkeypatch.setattr(watcher_hooks, "archive_channel", lambda channel: None)


@pytest.fixture(autouse=True)
def _state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path / "state"))
    Path(os.environ["LEMONAID_CONFIG"]).write_text("")


def _run(steps, size=(120, 40)):
    async def run():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def _summary(app) -> str:
    summary = app.query_one("#attention_summary", Static)
    return str(summary.render()) if summary.display else ""


def _folds(status: str, unread: bool = False) -> bool:
    n = db.Notification(1, "c:x", "", status="unread" if unread else "read")
    shown, folded = order.fold([n], {"c:x": status}, (), _RULE, (), ())
    return bool(folded)


@pytest.mark.parametrize("status", ["alert", "blocked", "merge", "approve", "running"])
def test_a_status_that_needs_you_keeps_its_row(status):
    assert not _folds(status)


@pytest.mark.parametrize("status", ["review", "done", "idle", "active", "dead", ""])
def test_every_other_status_folds_once_read(status):
    assert _folds(status)


@pytest.mark.parametrize("status", ["review", "done", "idle", "active", ""])
def test_an_unread_lemon_folds_unless_its_status_needs_you(status):
    assert _folds(status, unread=True)


def test_pinned_deaf_and_focused_lemons_keep_their_rows():
    rows = [db.Notification(i, f"c:{i}", "", status="read") for i in range(4)]
    statuses = {n.channel: "done" for n in rows}

    shown, folded = order.fold(rows, statuses, {"c:0"}, _RULE, {"c:1"}, {"c:2"})

    assert [n.channel for n in shown] == ["c:0", "c:1", "c:2"]
    assert [n.channel for n in folded] == ["c:3"]


def test_the_state_starts_off_and_survives_a_save(tmp_path):
    where = tmp_path / "inbox.json"
    assert not attention.load(where)

    attention.save(True, where)
    assert attention.load(where)

    where.write_text("{not json")
    assert not attention.load(where)


def test_the_key_folds_what_doesnt_need_you_and_draws_the_summary():
    with db.connect() as conn:
        blocked = _session(conn, "blocked", age=40)
        review = _session(conn, "review", age=30)
        done = _session(conn, "done", age=20, unread=True)
        idle = _session(conn, "idle", age=10)
        _brief(conn, blocked, "blocked")
        _brief(conn, review, "review")
        _brief(conn, done, "done")

    async def steps(app, pilot):
        before = sorted(app._row_channels())
        await pilot.press("exclamation_mark")
        await pilot.pause()
        on = sorted(app._row_channels()), _summary(app), app.query_one("#fold_label").display
        await pilot.press("w")
        await pilot.pause()
        opened = sorted(app._row_channels())
        await pilot.press("w", "exclamation_mark")
        await pilot.pause()
        return before, on, opened, sorted(app._row_channels()), _summary(app)

    before, (rows, summary, fold_line), opened, off, summary_off = _run(steps)

    assert before == sorted([blocked, review, done, idle])
    assert rows == [blocked]
    assert summary.split() == ["○1", "w", "shows", "all", "?1", "r1", "d1"]
    assert not fold_line
    assert opened == before
    assert off == before and summary_off == ""
    assert json.loads(attention.path().read_text()) == {"attention": False}


def test_a_slow_first_save_doesnt_overwrite_the_later_choice(monkeypatch):
    """Two quick toggles: the first save is held until the second toggle, and the file says off."""
    first_started = threading.Event()
    release = threading.Event()
    real_save = attention.save
    calls: list[bool] = []

    def held_save(on: bool, where=None) -> None:
        calls.append(on)
        if len(calls) == 1:
            first_started.set()
            release.wait(5)
        real_save(on, where)

    monkeypatch.setattr(attention, "save", held_save)

    async def steps(app, pilot):
        await pilot.press("exclamation_mark")
        await asyncio.to_thread(first_started.wait, 5)
        await pilot.press("exclamation_mark")
        await pilot.pause()
        release.set()
        await app.workers.wait_for_complete()
        return app._content.inbox.attention

    assert _run(steps) is False
    assert attention.load() is False


def test_the_mode_comes_back_on_after_a_restart():
    attention.save(True)
    with db.connect() as conn:
        review = _session(conn, "review", age=30)
        running = _session(conn, "running", age=20)
        _brief(conn, review, "review")
        _brief(conn, running, "running")

    async def steps(app, pilot):
        return app._row_channels()

    assert _run(steps) == [running]


def test_an_unread_lemon_without_a_status_folds_and_is_counted():
    attention.save(True)
    with db.connect() as conn:
        blocked = _session(conn, "blocked", age=30)
        _session(conn, "idle", age=10, unread=True)
        _brief(conn, blocked, "blocked")

    async def steps(app, pilot):
        return app._row_channels(), _summary(app)

    channels, summary = _run(steps)
    assert channels == [blocked]
    assert summary.split() == ["○1", "w", "shows", "all", "?1"]


def test_a_folded_lemons_grove_key_still_switches_to_it(monkeypatch):
    attention.save(True)
    with db.connect() as conn:
        blocked = _session(conn, "blocked", age=30)
        done = _session(conn, "done", age=10)
        _brief(conn, blocked, "blocked")
        _brief(conn, done, "done")
    chosen: list[str] = []
    monkeypatch.setattr(LemonaidApp, "_activate_lemon", lambda self, n: chosen.append(n.channel))

    async def steps(app, pilot):
        drawn = app._row_channels()
        for character in inbox_keys.names(app._content.inbox.grove)[done]:
            await pilot.press(character)
            await pilot.pause()
        return drawn

    assert _run(steps) == [blocked]
    assert chosen == [done]


def test_the_sidebar_summary_draws_header_badges_and_one_count_for_the_rest():
    rows = [db.Notification(i, f"c:{i}", "", status="read") for i in range(5)]
    statuses = {"c:0": "blocked", "c:1": "done", "c:2": "idle", "c:3": "active", "c:4": ""}

    line = attention_summary.line(rows, statuses, ["blocked", "running"], True, "w", False, {}, 4)

    assert line.plain == "  ?1  │ d1  ○3  w"
    assert (line.spans[0].start, line.spans[0].end) == (1, 5)  # the glyph and its number, one style


def test_the_summary_puts_each_badge_in_its_group_bar_slot():
    rows = [db.Notification(i, f"c:{i}", "", status="read") for i in range(3)]
    statuses = {"c:0": "blocked", "c:1": "done", "c:2": "idle"}
    starts = group_headers.slot_starts(60, [60], 0, 0, 4)

    line = attention_summary.line(rows, statuses, ["blocked"], True, "w", False, starts, 4)

    assert line.plain.index("?1") == starts["blocked"] + 1
    assert line.plain.index("d1") == starts["done"] + 1
    assert line.plain.startswith(" ○1  w")


def test_inbox_totals_past_nine_widen_the_shared_slots_and_stay_whole():
    group = groups.store.Group(1, "Work", 0, (), color="#c8a0f0")
    header = sections.Header(group, 3, (("blocked", 1), ("running", 1), ("merge", 1)))
    statuses = {
        **{f"c:b{i}": "blocked" for i in range(12)},
        **{f"c:r{i}": "running" for i in range(12)},
        "c:m": "merge",
    }
    rows = [db.Notification(i, channel, "", status="read") for i, channel in enumerate(statuses)]
    slot = max(group_headers.slot_width([header]), attention_summary.slot_width(rows, statuses))
    starts = group_headers.slot_starts(60, [60], 0, 0, slot)

    line = attention_summary.line(rows, statuses, ["blocked"], True, "w", False, starts, slot).plain

    assert slot == 5
    assert line.index("N12") + 3 == starts["running"] + slot - 1
    assert "?12" in line


def test_the_selected_row_keeps_its_place_until_the_cursor_leaves_it():
    attention.save(True)
    with db.connect() as conn:
        blocked = _session(conn, "blocked", age=30)
        running = _session(conn, "running", age=10)
        _brief(conn, blocked, "blocked")
        _brief(conn, running, "running")

    async def steps(app, pilot):
        while app._selected_channel() != running:
            await pilot.press("down")
            await pilot.pause()
        with db.connect() as conn:
            _brief(conn, running, "done")
        app._refresh_notifications()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        selected = app._row_channels(), app._selected_channel()
        await pilot.press("up")
        app._refresh_notifications()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        return selected, app._row_channels()

    selected, left = _run(steps)

    assert selected == ([blocked, running], running)
    assert left == [blocked]


def test_a_row_chosen_by_search_stays_after_the_search_closes():
    attention.save(True)
    with db.connect() as conn:
        blocked = _session(conn, "blocked", age=30)
        done = _session(conn, "finished", age=10)
        _brief(conn, blocked, "blocked")
        _brief(conn, done, "done")

    async def steps(app, pilot):
        for key in ("slash", *"finished", "escape"):
            await pilot.press(key)
            await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        return app._row_channels(), app._selected_channel()

    assert _run(steps) == ([blocked, done], done)
