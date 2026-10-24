"""The periodic refresh reads on a worker, so another process's database lock never holds input."""

import asyncio
import sqlite3
import time

from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp


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
