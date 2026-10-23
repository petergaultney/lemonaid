"""Two sessions with no brief, sharing a name, tty and window, can be grouped in `lma`."""

import pytest
from textual.widgets import DataTable

from lemonaid import groups
from lemonaid.inbox import db

from .shared import channels, keep_sessions, run  # noqa: F401

_TWO = ("claude:6dd09c59", "claude:e82424f9")


@pytest.fixture
def stray() -> None:
    with db.connect() as conn:
        for channel in _TWO:
            db.add(
                conn,
                channel,
                "Started",
                "quiet-push-no-prompt",
                {"tty": "/dev/ttys191", "cwd": "/tmp/exp", "tmux_session": "quiet-push-no-prompt"},
            )
        conn.execute("UPDATE notifications SET switch_source = 'tmux', status = 'read'")
        conn.commit()


def test_plus_groups_each_session_by_channel(stray):
    async def steps(app, pilot):
        await pilot.pause()
        for channel in _TWO:
            app.query_one("#main_table", DataTable).move_cursor(row=channels(app).index(channel))
            await pilot.press("plus")
            await pilot.pause()
            await pilot.press(*"stray", "enter")
            await pilot.pause()

    run(steps)

    with db.connect() as conn:
        assert {g.name: set(g.members) for g in groups.store.all_groups(conn)} == {
            "stray": set(_TWO)
        }
