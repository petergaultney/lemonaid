"""Tests for responsive column sizing in the inbox tables."""

import asyncio

from rich.text import Text

from lemonaid.inbox.tui.app import (
    _MEDIUM_LAYOUT_COLS,
    _SIDEBAR_COLS,
    _WIDE_LAYOUT_COLS,
    LemonaidApp,
)


def _widths(width: int) -> dict[str, int]:
    """Run the app at a given terminal width and return visible column widths."""

    async def run() -> dict[str, int]:
        app = LemonaidApp()
        async with app.run_test(size=(width, 26)) as pilot:
            await pilot.pause()
            await pilot.pause()
            table = app.query_one("#main_table")
            return {
                c.label.plain: c.width for c in table.columns.values() if c.width and c.label.plain
            }

    return asyncio.run(run())


def _row_width(width: int) -> int:
    """The virtual row width DataTable reports, which is what triggers h-scrolling.

    Asks Textual rather than recomputing the padding by hand: an independent
    estimate here can agree with itself while disagreeing with the widget, which is
    how a horizontal scrollbar went unnoticed.
    """

    async def run() -> int:
        app = LemonaidApp()
        async with app.run_test(size=(width, 26)) as pilot:
            await pilot.pause()
            await pilot.pause()
            table = app.query_one("#main_table")
            return sum(c.get_render_width(table) for c in table.columns.values())

    return asyncio.run(run())


def _content_width(width: int) -> int:
    """Width the table can actually paint into, after the vertical scrollbar."""

    async def run() -> int:
        app = LemonaidApp()
        async with app.run_test(size=(width, 26)) as pilot:
            await pilot.pause()
            await pilot.pause()
            return app.query_one("#main_table").scrollable_content_region.width

    return asyncio.run(run())


def test_row_never_exceeds_paintable_width():
    """Overflow costs a row of height, not just a horizontal scrollbar.

    The comparison is against the scrollable content region, not the terminal
    width: the vertical scrollbar takes two columns, so a row sized to the full
    terminal overflows by exactly that much and DataTable answers with a
    horizontal scrollbar that eats the bottom row of the list.
    """
    for width in (60, 80, 96, 100, 120, 160, 200):
        assert _row_width(width) <= _content_width(width), width


def test_narrow_layout_drops_weakest_columns_for_name():
    """At 80 columns Name matters more than TTY, Branch, or Message."""
    widths = _widths(80)
    assert "TTY" not in widths
    assert "Branch" not in widths
    assert "Message" not in widths
    assert widths["Name"] > 30


def test_medium_layout_keeps_message_but_not_tty():
    widths = _widths(_MEDIUM_LAYOUT_COLS)
    assert "TTY" not in widths
    assert "Message" in widths
    assert "Branch" in widths


def test_wide_layout_shows_every_column():
    widths = _widths(_WIDE_LAYOUT_COLS)
    assert {"Time", "Name", "Branch", "CWD", "Message", "TTY"} <= set(widths)


def test_name_grows_with_width_within_a_layout():
    """Name is not strictly monotonic across layout thresholds.

    Crossing a threshold re-introduces a column (Message at the medium
    threshold, TTY at the wide one), which necessarily takes space back from
    Name. That trade is deliberate, so growth is only asserted within a layout.
    """
    assert (
        _widths(_SIDEBAR_COLS)["Name"]
        < _widths(88)["Name"]
        < _widths(_MEDIUM_LAYOUT_COLS - 1)["Name"]
    )
    assert _widths(_MEDIUM_LAYOUT_COLS)["Name"] < _widths(_WIDE_LAYOUT_COLS - 1)["Name"]
    assert _widths(_WIDE_LAYOUT_COLS)["Name"] < _widths(200)["Name"]


def test_name_beats_original_fixed_width_everywhere():
    """The whole point of the change: Name is never back to its old 14 chars.

    23 rather than 24 at the narrow end: two of those columns belong to the
    vertical scrollbar, which the layout now reserves instead of overflowing into.
    """
    for width in (_SIDEBAR_COLS, 80, 100, _MEDIUM_LAYOUT_COLS, 120, _WIDE_LAYOUT_COLS, 160, 200):
        assert _widths(width)["Name"] >= 23, width


def test_name_is_widest_flex_column_when_wide():
    widths = _widths(160)
    assert widths["Name"] > widths["Message"]
    assert widths["Name"] > widths["CWD"]


def test_no_horizontal_scrollbar_steals_a_row():
    """The symptom that surfaced this: a blank line under the last session.

    A one-cell overflow makes DataTable show a horizontal scrollbar, which renders
    as an empty row between the list and the status bar and hides a session.
    """

    async def run(width: int, height: int) -> tuple[bool, int]:
        app = LemonaidApp()
        async with app.run_test(size=(width, height)) as pilot:
            await pilot.pause()
            await pilot.pause()
            table = app.query_one("#main_table")
            table._update_dimensions(list(table.rows.keys()))
            await pilot.pause()
            return table.show_horizontal_scrollbar, table.scrollable_content_region.height

    # Short terminals are where it bites: enough rows to force the vertical
    # scrollbar, which is what pushed the row width over the edge.
    for width in (80, 100, 120, 132, 160, 200):
        for height in (12, 14, 20):
            hbar, content_height = asyncio.run(run(width, height))
            assert not hbar, (width, height)
            # Header, and the row the status text shares with the footer.
            assert content_height == height - 2, (width, height, content_height)


def test_snoozed_table_keeps_its_wake_column_when_narrow():
    """The wake time is the point of the snoozed view, unlike a TTY."""

    async def run() -> Text:
        app = LemonaidApp()
        async with app.run_test(size=(80, 26)) as pilot:
            await pilot.pause()
            table = app.query_one("#snoozed_table")
            return list(table.columns.values())[7].label

    assert asyncio.run(run()).plain == "Wakes"


def test_a_wide_terminal_gives_its_surplus_to_the_message():
    """Name padded to 90 columns while the message truncated was the complaint."""
    at_250 = _widths(250)

    assert at_250["Message"] > at_250["Name"]


def test_capped_columns_stop_growing_but_the_message_does_not():
    wide, wider = _widths(200), _widths(250)

    assert wide["Name"] == wider["Name"]  # capped
    assert wider["Message"] > wide["Message"]  # unbounded
