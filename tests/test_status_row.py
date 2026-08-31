"""Tests for the bottom row shared by the key hints and the status text."""

import asyncio

from textual.containers import VerticalScroll
from textual.widgets import Footer, Static

from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.help_screen import HelpScreen


def _run(steps, size=(120, 20)):
    """Drive the app, calling `steps(app, pilot)` once it has settled."""

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def test_key_hints_start_visible():
    async def steps(app, pilot):
        return app.query_one(Footer).display, app.query_one("#status", Static).display

    footer, status = _run(steps)
    assert footer
    assert not status


def test_status_takes_the_row_once_hints_time_out():
    async def steps(app, pilot):
        app._show_keys(False)
        await pilot.pause()
        return app.query_one(Footer).display, app.query_one("#status", Static).display

    footer, status = _run(steps)
    assert not footer
    assert status


def test_status_and_footer_share_the_bottom_row():
    """The point of the change: one row, not two.

    Checks the row each one lands on, not merely that one is hidden: an undocked
    #status also hides correctly while still reserving its own row of height.
    """

    async def steps(app, pilot):
        table_heights, rows = [], []
        for _ in range(2):
            visible = [
                w for w in (app.query_one(Footer), app.query_one("#status", Static)) if w.display
            ]
            assert len(visible) == 1, visible
            rows.append(visible[0].region.y)
            table_heights.append(app.query_one("#main_table").region.height)
            await pilot.press("question_mark")
            await pilot.pause()
        return rows, table_heights, app.size.height

    rows, table_heights, screen_height = _run(steps)
    # Both land on the last row, and the table keeps the same height either way.
    assert rows == [screen_height - 1, screen_height - 1], rows
    assert table_heights[0] == table_heights[1], table_heights
    # Header plus the one shared row is all the chrome above/below the table.
    assert table_heights[0] == screen_height - 2, table_heights


def test_question_mark_opens_the_key_reference():
    """The footer truncates in a sidebar, so the full list is a modal."""

    async def steps(app, pilot):
        await pilot.press("question_mark")
        await pilot.pause()
        return isinstance(app.screen, HelpScreen)

    assert _run(steps)


def test_escape_closes_the_reference_and_not_the_app():
    """Escape quits the app, so the modal has to stop the key reaching it."""

    async def steps(app, pilot):
        await pilot.press("question_mark")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        return isinstance(app.screen, HelpScreen), app.is_running

    still_up, running = _run(steps)
    assert not still_up
    assert running


def test_the_reference_closes_on_q_and_on_question_mark():
    async def steps(app, pilot, key):
        await pilot.press("question_mark")
        await pilot.pause()
        await pilot.press(key)
        await pilot.pause()
        return isinstance(app.screen, HelpScreen)

    assert not _run(lambda a, p: steps(a, p, "q"))
    assert not _run(lambda a, p: steps(a, p, "question_mark"))


def test_an_arrow_scrolls_the_reference_rather_than_closing_it():
    """A sidebar's column scrolls, so arrows have to reach the rest of it."""

    async def steps(app, pilot):
        await pilot.press("question_mark")
        await pilot.pause()
        for key in ("down", "up", "pagedown"):
            await pilot.press(key)
            await pilot.pause()
        return isinstance(app.screen, HelpScreen)

    assert _run(steps)


def test_an_arrow_moves_the_reference_down():
    """Not closing is half of it; the column has to actually move."""

    async def steps(app, pilot):
        await pilot.press("question_mark")
        await pilot.pause()
        column = app.screen.query_one(VerticalScroll)
        for _ in range(5):
            await pilot.press("down")
            await pilot.pause()
        return column.max_scroll_y, column.scroll_offset.y

    # Narrow: the scrolling column is the sidebar's layout, not the top bar's.
    reachable, moved = _run(steps, size=(58, 20))
    assert reachable > 0, "nothing below the fold - the test pane is too tall"
    assert moved > 0


def test_opening_the_reference_yields_the_footer_row_to_the_status():
    async def steps(app, pilot):
        await pilot.press("question_mark")
        await pilot.pause()
        return app.query_one(Footer).display, app.query_one("#status", Static).display

    footer, status = _run(steps)
    assert not footer
    assert status


def test_opening_the_reference_cancels_the_startup_timeout():
    """Otherwise the timer would swap the row back while the modal is up."""

    async def steps(app, pilot):
        assert app._hint_timer is not None
        await pilot.press("question_mark")
        await pilot.pause()
        return app._hint_timer

    assert _run(steps) is None


def test_status_text_survives_a_hint_toggle():
    async def steps(app, pilot):
        app._set_status("7 unread, 3 read")
        app._show_keys(True)
        await pilot.pause()
        app._show_keys(False)
        await pilot.pause()
        return str(app.query_one("#status", Static).render())

    assert _run(steps) == "7 unread, 3 read"
