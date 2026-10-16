"""A search draws matches under their groups and counts each lemon once."""

from textual.widgets import Static

from lemonaid import groups
from lemonaid.inbox import db

from .shared import channels, keep_sessions, run, session  # noqa: F401


def test_a_lemon_in_two_groups_is_one_search_match():
    with db.connect() as conn:
        lemon = session(conn, "needle", "")
        session(conn, "other", "")
        for name in ("A", "B"):
            groups.store.add(conn, groups.store.create(conn, name), [lemon])

    async def steps(app, pilot):
        await pilot.press("/", "n", "e", "e", "d", "l", "e")
        await pilot.pause()
        assert channels(app) == ["", "claude:needle", "", "claude:needle"]
        assert "1 inbox match" in str(app.query_one("#status", Static).content)

    run(steps)
