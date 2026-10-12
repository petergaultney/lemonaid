"""Helpers for driving `lma` over sessions with briefs, as the group tests do."""

import asyncio
import itertools
import time

import pytest

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.watchers import watcher_hooks

_ids = itertools.count(900)


def session(conn, name: str, status: str, *, unread: bool = False) -> str:
    """A session with an attached brief at *status*. Returns its Lemon-ID."""
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
        ("unread" if unread else "read", time.time(), n.id),
    )
    conn.commit()
    path = brief_store.briefs_dir() / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {name}\n\nStatus: {status}\n\n## Now\n")
    attached.attach(conn, channel, path)
    return identity.ensure(conn, path)


@pytest.fixture(autouse=True)
def keep_sessions(monkeypatch):
    """The test tmux has none of these ttys, so the watcher would archive every row."""
    monkeypatch.setattr(watcher_hooks, "archive_channel", lambda channel: None)


def run(steps, size=(120, 40)):
    async def steps_run():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(steps_run())


def channels(app) -> list[str]:
    return app._row_channels()
