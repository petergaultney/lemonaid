"""Timestamps say which day, and the gutter says which pane you are in."""

import time
from datetime import datetime, timedelta

from lemonaid.inbox.tui.app import _format_timestamp, _time_cell
from lemonaid.inbox.tui.utils import HERE_BAR, HERE_BAR_STYLE, HERE_BLOCK, jump_gutter


def _at(dt: datetime) -> float:
    return dt.timestamp()


def test_today_shows_a_clock_time():
    assert _format_timestamp(time.time()).count(":") == 2


def test_yesterday_keeps_its_time_behind_a_day_marker():
    """The hour is the useful part this recently; the marker says which day."""
    late_yesterday = (datetime.now() - timedelta(days=1)).replace(hour=23, minute=59)
    assert _format_timestamp(_at(late_yesterday)) == "y 23:59"


def test_older_than_yesterday_becomes_a_date():
    three_days = datetime.now() - timedelta(days=3)
    assert _format_timestamp(_at(three_days)) == three_days.strftime("%Y-%m-%d")


def test_a_moment_ago_is_still_today_across_the_hour():
    assert _format_timestamp(time.time() - 3600).count(":") == 2


def test_a_recent_date_keeps_the_live_colour():
    """Yesterday at 23:59 is a date by morning, but has not gone cold."""
    cell = _time_cell(time.time() - 8 * 3600, False)
    assert cell.style == "green"


def test_an_old_date_goes_grey():
    cell = _time_cell(time.time() - 40 * 86400, False)
    assert cell.style == "bright_black"


def test_the_gutter_numbers_a_row_you_can_jump_to():
    assert jump_gutter(0).plain == "1 "


def test_the_focused_row_is_marked_instead_of_numbered():
    """One row is one line tall, so its mark is the heavier glyph."""
    gutter = jump_gutter(0, is_here=True)
    assert "1" not in gutter.plain
    assert gutter.plain == f"{HERE_BLOCK} "
    assert gutter.spans[0].style == HERE_BAR_STYLE


def test_the_focused_gutter_is_the_width_of_the_digit_it_replaces():
    assert len(jump_gutter(0, is_here=True).plain) == len(jump_gutter(0).plain)


def test_the_gutter_style_does_not_run_on_into_the_name():
    """Concatenation takes the left operand's base style for the whole result.

    A background set as the gutter's own style would paint the name too - the
    same way an empty bold marker once carried bold into every session name.
    """
    from lemonaid.inbox.tui.utils import styled_cell

    combined = jump_gutter(0, is_here=True) + styled_cell("a-name", False, "name")
    assert combined.style == ""
    assert combined.spans[0].end == 1


def test_the_marker_keeps_the_name_column_aligned():
    assert len(jump_gutter(0, is_here=True).plain) == len(jump_gutter(0).plain)


def test_the_cursor_does_not_repaint_the_row_it_marks():
    """Textual's default gives the cursor's foreground priority over the cell's.

    Colour is the field's identity here, so a selected row that adopts one
    foreground loses the distinction the list is read for.
    """
    from lemonaid.inbox.tui.table import ClickToActTable

    assert ClickToActTable().cursor_foreground_priority == "renderable"


def test_the_selected_row_keeps_each_field_its_own_colour():
    """The regression this guards is invisible in the cell styles.

    The flattening happens when Textual composites the cursor over the row, so
    the check has to read the segments that actually reach the screen rather
    than the Text objects handed to the table.
    """
    import asyncio

    from lemonaid.inbox import db
    from lemonaid.inbox.tui import app as tui

    async def run():
        with db.connect() as conn:
            for i in range(2):
                db.add(
                    conn,
                    channel=f"claude:sess{i}",
                    message="doing a thing",
                    name=f"session-{i}",
                    metadata={"cwd": "/tmp/somewhere", "git_branch": "a-branch"},
                    switch_source="tmux",
                )

        pane = tui.LemonaidApp()
        pane._archive_channel = lambda channel: None
        async with pane.run_test(size=(150, 20)) as pilot:
            await pilot.pause()
            await pilot.pause()
            table = pane.query_one("#main_table")
            assert table.row_count == 2
            assert table.cursor_coordinate.row == 0

            # The cursor sits on the first data row, which the header puts two
            # lines down: one for the app's own title bar, one for the column
            # headings.
            strip = pane.screen._compositor.render_strips()[2]
            return {
                str(segment.style.color.name)
                for segment in strip
                if segment.text.strip() and segment.style and segment.style.color
            }

    colours = asyncio.run(run())
    assert len(colours) > 1, f"the cursor flattened the selected row to {colours}"


def test_a_card_draws_a_thin_rule_where_a_row_fills_its_gutter():
    """The two layouts give the same mark different room, so it takes two forms."""
    from rich.text import Text

    from lemonaid.inbox.tui.app import _as_card
    from lemonaid.inbox.tui.utils import styled_cell

    cells = [
        Text("09:00"),
        Text(""),
        Text("CC"),
        jump_gutter(0, True) + styled_cell("a-session", False, "name"),
        Text(""),
        Text("~/w/x"),
        Text("a message"),
        Text(""),
    ]
    context = _as_card(cells, 44, 1, 1, 2)[0].plain.split("\n")[1]

    assert context.startswith(HERE_BAR)
    assert HERE_BLOCK not in context


def test_a_focused_card_carries_the_bar_down_every_line():
    """A card is several lines tall, so a bar on its first line marks nothing.

    The name it is built from is one line; the bar has to be re-laid on the
    context and message lines or it reads as a stray glyph beside the name.
    """
    from rich.text import Text

    from lemonaid.inbox.tui.app import _as_card
    from lemonaid.inbox.tui.utils import styled_cell

    def card_for(is_here: bool) -> list[str]:
        cells = [
            Text("09:00"),
            Text("●"),
            Text("CC"),
            jump_gutter(0, is_here) + styled_cell("a-session", False, "name"),
            Text("a-branch"),
            Text("~/w/x"),
            Text("a message"),
            Text(""),
        ]
        return _as_card(cells, 44, 1, 1)[0].plain.split("\n")

    focused = card_for(True)
    assert all(line.startswith(HERE_BAR) for line in focused if line)

    # Including the blank line that separates it from the next card, which
    # takes the row cursor's background along with the rest of the cell.
    assert focused[-1] == HERE_BAR

    plain = card_for(False)
    assert not any(HERE_BAR in line for line in plain)


def test_a_marked_card_keeps_its_name_on_the_same_column():
    """The bar replaces the digit's ink, not the space the digit occupied."""
    from rich.text import Text

    from lemonaid.inbox.tui.app import _as_card
    from lemonaid.inbox.tui.utils import styled_cell

    def headline(is_here: bool) -> str:
        cells = [
            Text("09:00"),
            Text(""),
            Text("CC"),
            jump_gutter(0, is_here) + styled_cell("a-session", False, "name"),
            Text(""),
            Text("~/w/x"),
            Text("a message"),
            Text(""),
        ]
        return _as_card(cells, 44, 1, 1, 2)[0].plain.split("\n")[0]

    assert headline(True).index("a-session") == headline(False).index("a-session")


def test_an_unmarked_card_still_ends_in_a_genuinely_empty_line():
    """The separator only grows a bar when there is a bar to carry."""
    from rich.text import Text

    from lemonaid.inbox.tui.app import _as_card
    from lemonaid.inbox.tui.utils import styled_cell

    cells = [
        Text("09:00"),
        Text(""),
        Text("CC"),
        jump_gutter(0, False) + styled_cell("a-session", False, "name"),
        Text(""),
        Text("~/w/x"),
        Text("a message"),
        Text(""),
    ]

    assert _as_card(cells, 44, 1, 1, 2)[0].plain.endswith("\n")


def test_the_bar_does_not_close_up_a_card_line_it_marks():
    """The bar is prepended, not swapped for the indent the body lines keep.

    Consuming that column ran the bar straight into the timestamp beside it.
    """
    from rich.text import Text

    from lemonaid.inbox.tui.app import _as_card
    from lemonaid.inbox.tui.utils import styled_cell

    def lines(is_here: bool) -> list[str]:
        cells = [
            Text("15:24"),
            Text(""),
            Text("CC"),
            jump_gutter(0, is_here) + styled_cell("a-name", False, "name"),
            Text(""),
            Text("~/w"),
            Text("msg"),
        ]
        return _as_card(cells, 40, 1, 1, 2)[0].plain.split("\n")

    marked, plain = lines(True), lines(False)
    assert marked[1] == HERE_BAR + plain[1]
    assert marked[2] == HERE_BAR + plain[2]


def test_an_unmarked_card_keeps_its_jump_digit():
    """Only the here-marker comes off the name; the digit is shown as-is.

    A card strips the gutter so it can draw its own edge, and stripping
    unconditionally took every card's number with it.
    """
    from rich.text import Text

    from lemonaid.inbox.tui.app import _as_card
    from lemonaid.inbox.tui.utils import styled_cell

    def headline(is_here: bool, row: int) -> str:
        cells = [
            Text("15:24"),
            Text(""),
            Text("CC"),
            jump_gutter(row, is_here) + styled_cell("a-name", False, "name"),
            Text(""),
            Text("~/w"),
            Text("msg"),
        ]
        return _as_card(cells, 40, 1, 1, 2)[0].plain.split("\n")[0]

    assert "2" in headline(False, 1)
    assert "1" not in headline(True, 0)


def test_a_marked_card_truncates_rather_than_wrapping_past_the_pane():
    """The bar is a column of the card's width, not an extra one beside it.

    A line budgeted as though the bar were free overflows the pane and wraps,
    and a wrapped line starts at column 0 - breaking the edge mid-card.
    """
    from rich.text import Text

    from lemonaid.inbox.tui.app import _as_card
    from lemonaid.inbox.tui.utils import styled_cell

    width = 44

    def lines(is_here: bool, row: int) -> list[str]:
        cells = [
            Text("09:59:08"),
            Text(""),
            Text("CC"),
            jump_gutter(row, is_here) + styled_cell("a-long-session-name-here", False, "name"),
            Text("a-branch-that-is-long"),
            Text("~/w/d/main"),
            Text("a message"),
        ]
        return _as_card(cells, width, 1, 1, 2)[0].plain.split("\n")

    for line in lines(True, 0):
        assert len(line) <= width
