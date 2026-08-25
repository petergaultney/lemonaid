"""The bar above the list, which says what the list is and whether it wants you.

It is the table's header row - empty of labels in card layout - rather than the
app's title bar. Colour lives in the stylesheet; what most of these pin is the
class the app puts on itself, since that is the part a refresh has to keep in
step with the rows.
"""

import asyncio

from textual.color import Color
from textual.widgets import DataTable

from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp


def _add(status: str = "unread") -> None:
    with db.connect() as conn:
        notification = db.add(conn, "claude", "a message", "a-session", {"tty": "/dev/ttys001"})
        conn.execute(
            "UPDATE notifications SET status = ?, switch_source = ? WHERE id = ?",
            (status, "tmux", notification.id),
        )
        conn.commit()


def _bar(app, table_id: str) -> Color:
    """The colour actually painted behind the list's header row."""
    return app.query_one(table_id, DataTable).get_component_styles(
        "datatable--header"
    ).background


def _run(steps):
    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 20)) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def test_an_empty_inbox_is_not_unread():
    async def steps(app, pilot):
        return app.has_class("-unread")

    assert not _run(steps)


def test_an_unread_session_marks_the_header():
    _add("unread")

    async def steps(app, pilot):
        return app.has_class("-unread")

    assert _run(steps)


def test_a_read_session_leaves_the_header_alone():
    _add("read")

    async def steps(app, pilot):
        return app.has_class("-unread")

    assert not _run(steps)


def test_reading_the_last_unread_session_clears_the_header():
    """Otherwise the bar keeps demanding attention for a list that has none."""
    _add("unread")

    async def steps(app, pilot):
        before = app.has_class("-unread")
        await pilot.press(app.config.tui.keybindings.mark_read[0])
        await pilot.pause()
        return before, app.has_class("-unread")

    before, after = _run(steps)
    assert before
    assert not after


def test_history_outranks_an_unread_inbox():
    """Both style the same bar. History is a record of things already dealt
    with, so which list you are looking at is the fact worth the colour - and
    the inbox's own state is still there when you come back to it."""
    _add("unread")

    async def steps(app, pilot):
        app._set_history_mode(True)
        await pilot.pause()
        in_history = _bar(app, "#history_table")
        app._set_history_mode(False)
        await pilot.pause()
        return in_history, _bar(app, "#main_table")

    in_history, back_in_inbox = _run(steps)
    assert in_history == Color.parse("ansi_blue")
    assert back_in_inbox == Color.parse("ansi_bright_red")
