"""The periodic refresh reads on a worker, so another process's database lock never holds input."""

import asyncio
import sqlite3
import threading
import time

import pytest

from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.live import changes, inbox_frame, inbox_list
from lemonaid.inbox.tui.watchers import watcher_hooks
from lemonaid.watch import kqueue_waits


def _add(name: str) -> None:
    with db.connect() as conn:
        db.add(conn, f"claude:{name}", "message", name, {"cwd": "/tmp"})


def test_a_locked_database_delays_the_refresh_but_not_the_app():
    _add("worker")

    async def run() -> tuple[float, int]:
        app = LemonaidApp()
        async with app.run_test(size=(120, 20)) as pilot:
            await pilot.pause()
            locker = sqlite3.connect(db.get_db_path())
            locker.execute("BEGIN EXCLUSIVE")
            try:
                worst = 0.0
                for _ in range(12):  # a few refresh ticks
                    sent = time.monotonic()
                    answered = asyncio.Event()
                    app.call_later(answered.set)
                    await answered.wait()
                    worst = max(worst, time.monotonic() - sent)
                    await asyncio.sleep(0.1)
                stalled = app._ticks.busy
            finally:
                locker.rollback()
            return worst, stalled

    worst, stalled = asyncio.run(run())

    assert stalled, "a tick should be waiting on the lock"
    assert worst < 0.3


def test_an_immediate_redraw_does_not_wait_for_a_slow_background_read(monkeypatch):
    _add("worker")
    slow = threading.Event()
    loading = threading.Event()
    load = inbox_frame.load

    def slow_off_the_ui_thread(*args, **kwargs):
        if threading.current_thread() is not threading.main_thread():
            loading.set()
            slow.wait(5)
        return load(*args, **kwargs)

    async def run() -> float:
        app = LemonaidApp()
        async with app.run_test(size=(120, 20)) as pilot:
            await pilot.pause()
            monkeypatch.setattr(inbox_frame, "load", slow_off_the_ui_thread)
            try:
                await asyncio.to_thread(loading.wait, 5)
                started = time.monotonic()
                app.action_toggle_fold()
                return time.monotonic() - started
            finally:
                slow.set()

    assert asyncio.run(run()) < 0.3


def _count_draws(monkeypatch) -> list[float]:
    drawn: list[float] = []
    draw = inbox_list.InboxList.draw

    def counted(self, *args, **kwargs):
        drawn.append(time.monotonic())
        return draw(self, *args, **kwargs)

    monkeypatch.setattr(inbox_list.InboxList, "draw", counted)
    return drawn


def test_a_refresh_that_reads_what_is_drawn_draws_nothing_until_something_changes(monkeypatch):
    _add("worker")
    drawn = _count_draws(monkeypatch)

    async def run() -> tuple[int, int]:
        app = LemonaidApp()
        async with app.run_test(size=(120, 20)) as pilot:
            await pilot.pause(0.5)
            settled = len(drawn)
            await pilot.pause(1.5)  # several ticks with nothing new
            idle = len(drawn) - settled
            _add("reviewer")
            for _ in range(50):  # a loaded test machine can take a while to tick
                await pilot.pause(0.1)
                if len(drawn) > settled + idle:
                    break
            return idle, len(drawn) - settled - idle

    idle, changed = asyncio.run(run())

    assert idle == 0
    assert changed >= 1


def test_an_unchanged_frame_is_still_drawn_now_and_then_for_its_ages(monkeypatch):
    _add("worker")
    monkeypatch.setattr(inbox_list, "_REDRAW_SECONDS", 0.5)
    monkeypatch.setattr(changes, "FULL_SECONDS", 0.5)
    drawn = _count_draws(monkeypatch)

    async def run() -> int:
        app = LemonaidApp()
        async with app.run_test(size=(120, 20)) as pilot:
            await pilot.pause(0.5)
            settled = len(drawn)
            await pilot.pause(2.0)
            return len(drawn) - settled

    assert asyncio.run(run()) >= 2


def test_a_resize_draws_at_the_new_width_though_nothing_else_changed(monkeypatch):
    _add("worker")
    monkeypatch.setattr(watcher_hooks, "start", lambda *args: None)  # nothing else redraws
    monkeypatch.setattr(LemonaidApp, "_check_claude_patch", lambda self: None)
    widths: list[int] = []
    draw = inbox_list.InboxList.draw

    def counted(self, *args, **kwargs):
        widths.append(kwargs["width"])
        return draw(self, *args, **kwargs)

    monkeypatch.setattr(inbox_list.InboxList, "draw", counted)

    async def run() -> None:
        app = LemonaidApp()
        async with app.run_test(size=(60, 30)) as pilot:
            await pilot.pause(1.0)
            cards = app._content.cards
            await pilot.resize_terminal(65, 30)
            for _ in range(30):
                await pilot.pause(0.1)
                if 65 in widths:
                    break
            assert app._content.cards == cards  # a resize within one layout

    asyncio.run(run())

    assert 65 in widths


@pytest.mark.skipif(not kqueue_waits.available(), reason="without kqueue every tick loads")
def test_an_unchanged_detached_set_leaves_the_refresh_idle(tmp_path):
    app = LemonaidApp()
    app._changes = changes.Changes(db.get_db_path(), [tmp_path], changes.hub())
    try:
        app._set_detached_channels({"claude:a"})
        assert app._changes.due("request", 100.0)
        assert not app._changes.due("request", 100.1)

        app._set_detached_channels({"claude:a"})

        assert not app._changes.due("request", 100.2)

        app._set_detached_channels(set())

        assert app._changes.due("request", 100.3)
    finally:
        app._changes.close()
