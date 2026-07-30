"""Tests for responsive column sizing in the inbox tables."""

import asyncio

from rich.text import Text

from lemonaid.inbox.tui.app import (
    _MEDIUM_LAYOUT_COLS,
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
    async def run() -> int:
        app = LemonaidApp()
        async with app.run_test(size=(width, 26)) as pilot:
            await pilot.pause()
            await pilot.pause()
            table = app.query_one("#main_table")
            visible = [c for c in table.columns.values() if c.width]
            return sum(c.width for c in visible) + 2 * table.cell_padding * len(visible) + 1

    return asyncio.run(run())


def test_row_never_exceeds_terminal_width():
    """Overflowing the width would scroll the table horizontally."""
    for width in (60, 80, 96, 100, 120, 160, 200):
        assert _row_width(width) <= width, width


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
    assert _widths(60)["Name"] < _widths(80)["Name"] < _widths(_MEDIUM_LAYOUT_COLS - 1)["Name"]
    assert _widths(_MEDIUM_LAYOUT_COLS)["Name"] < _widths(_WIDE_LAYOUT_COLS - 1)["Name"]
    assert _widths(_WIDE_LAYOUT_COLS)["Name"] < _widths(200)["Name"]


def test_name_beats_original_fixed_width_everywhere():
    """The whole point of the change: Name is never back to its old 14 chars."""
    for width in (60, 80, 100, _MEDIUM_LAYOUT_COLS, 120, _WIDE_LAYOUT_COLS, 160, 200):
        assert _widths(width)["Name"] >= 24, width


def test_name_is_widest_flex_column_when_wide():
    widths = _widths(160)
    assert widths["Name"] > widths["Message"]
    assert widths["Name"] > widths["CWD"]


def test_snoozed_table_keeps_its_wake_column_when_narrow():
    """The wake time is the point of the snoozed view, unlike a TTY."""

    async def run() -> Text:
        app = LemonaidApp()
        async with app.run_test(size=(80, 26)) as pilot:
            await pilot.pause()
            table = app.query_one("#snoozed_table")
            return list(table.columns.values())[7].label

    assert asyncio.run(run()).plain == "Wakes"
