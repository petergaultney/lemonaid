"""Tests for the bottom row shared by the key hints and the status text."""

import asyncio

from textual.widgets import Footer, Static

from lemonaid.inbox.tui.app import LemonaidApp


def _run(steps):
    """Drive the app, calling `steps(app, pilot)` once it has settled."""

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 20)) as pilot:
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


def test_question_mark_toggles_hints_both_ways():
    async def steps(app, pilot):
        app._show_keys(False)
        await pilot.pause()
        states = []
        for _ in range(2):
            await pilot.press("question_mark")
            await pilot.pause()
            states.append(app.query_one(Footer).display)
        return states

    assert _run(steps) == [True, False]


def test_toggling_cancels_the_startup_timeout():
    """Otherwise the timer would yank the hints away mid-read."""

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
