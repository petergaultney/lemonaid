"""Rendering a session as a card, for panes shaped tall and narrow.

A card is as tall as its content needs, within a per-field budget, and ends in a
blank line. Padding every card to one height wasted most of a tall pane on blank
rows; the separator is what keeps them legible as separate entries instead.
"""

import asyncio

from rich.console import Console
from rich.text import Text

from lemonaid.inbox import db
from lemonaid.inbox.tui import app, backend_indicators
from lemonaid.inbox.tui.utils import (
    ATTENTION_COLOR,
    FIELD_STYLES,
    HERE_BAR,
    jump_gutter,
    styled_cell,
)
from lemonaid.tmux import scratch


def test_the_context_line_never_wraps():
    """It holds the fields you scan for, so it has to keep its one place."""
    cells = [
        Text("15:48:29"),
        Text(""),
        Text("CC"),
        Text("n"),
        Text("some/very/long/branch/name"),
        Text("~/w/d/t/live-observability"),
        Text("m"),
    ]
    (body,) = app._as_card(cells, 38, context_lines=3, message_lines=1)

    assert body.plain.split("\n")[1].endswith("…")
    assert len(body.plain.split("\n")) == 4  # name, context, message, separator


def test_a_card_stays_within_its_budget():
    cells = [
        Text("15:24:18"),
        Text(""),
        Text("CC"),
        Text("a name long enough to need truncating on any narrow pane"),
        Text("some/branch"),
        Text("~/w/some/path"),
        Text("a message that also runs well past the available width"),
        Text("ttys001"),
    ]
    (body,) = app._as_card(cells, 30, message_lines=3)

    # headline + one context line + message + the separator
    assert len(body.plain.split("\n")) <= 1 + 1 + 3 + 1
    assert body.plain.split("\n")[0].endswith("CC")


def test_a_card_ends_in_exactly_one_blank_line():
    """Two would read as a gap, none as a run-on into the next card."""
    cells = [Text("15:24"), Text(""), Text("CC"), Text("n"), Text(""), Text(""), Text("m")]
    (body,) = app._as_card(cells, 40)

    assert body.plain.endswith("\n")
    assert not body.plain.endswith("\n\n")


def test_a_wrap_landing_near_the_boundary_adds_no_second_blank():
    """rich pads a wrap to full width; that blank would read as a gap."""
    cells = [Text("15:24"), Text(""), Text("CC"), Text("n"), Text(""), Text(""), Text("a bc def")]
    (body,) = app._as_card(cells, 12, message_lines=3)

    assert not body.plain.endswith("\n\n")


def test_the_row_is_tall_enough_for_the_separator():
    cells = [Text("15:24"), Text(""), Text("CC"), Text("n"), Text(""), Text("~/w"), Text("m " * 40)]
    card = app._as_card(cells, 30, message_lines=3)

    assert app._row_height(card) == len(card[app._CARD_BODY_COLUMN].plain.split("\n"))


def test_a_short_card_does_not_pad_to_the_budget():
    """Padding is what made a tall pane mostly blank rows."""
    cells = [Text("15:24"), Text(""), Text("CC"), Text("n"), Text(""), Text("~/w"), Text("m")]
    (body,) = app._as_card(cells, 40, message_lines=3)

    lines = body.plain.split("\n")
    assert lines[0] == "   n" + " " * 34 + "CC"
    assert lines[1:] == [" 15:24 · ~/w", " m", ""]


def test_every_line_fits_the_width():
    cells = [Text("15:24:18"), Text(""), Text("CC")] + [Text("x" * 90)] * 5
    (body,) = app._as_card(cells, 24, message_lines=2)

    assert all(len(line) <= 24 for line in body.plain.split("\n"))


def test_an_unread_card_leads_with_its_marker():
    cells = [Text("15:24:18"), Text("●"), Text("CC"), Text("thing"), Text(""), Text(""), Text("")]
    (body,) = app._as_card(cells, 40)

    assert body.plain.split("\n")[0].startswith("  ● thing")


def test_a_read_card_keeps_the_name_aligned():
    """The marker column is a space when read, so names line up down the list."""
    cells = [Text("15:24:18"), Text(""), Text("CC"), Text("thing"), Text(""), Text(""), Text("")]
    (body,) = app._as_card(cells, 40)

    assert body.plain.split("\n")[0].startswith("   thing")
    assert body.plain.split("\n")[0].endswith("CC")


def test_empty_context_fields_are_dropped():
    """A session with no branch shouldn't render a dangling separator."""
    cells = [
        Text("15:24:18"),
        Text(""),
        Text("CC"),
        Text("thing"),
        Text(""),  # no branch
        Text("~/w/repo"),
        Text("msg"),
    ]
    (body,) = app._as_card(cells, 40)

    assert body.plain.split("\n")[1].strip() == "15:24:18 · ~/w/repo"


def test_a_card_keeps_the_colours_its_cells_arrived_with():
    """Both layouts read one palette, so a colour means the same thing in each."""
    cells = [
        styled_cell("15:24", True, "time"),
        Text("●"),
        styled_cell("CC", True, "backend"),
        styled_cell("a-name", True, "name"),
        styled_cell("a/branch", True, "branch"),
        styled_cell("~/w/repo", True, "cwd"),
        styled_cell("a message", True, "message"),
    ]
    (body,) = app._as_card(cells, 60)

    spans = {body.plain[s.start : s.end]: s.style for s in body.spans}
    # Against the palette rather than a copy of it: the claim is that a card
    # preserves the colour its cell arrived with, whatever that colour is.
    assert spans["a-name"] == f"bold {FIELD_STYLES['name']}"
    assert spans["15:24"] == f"bold {FIELD_STYLES['time']}"
    assert spans["~/w/repo"] == f"bold {FIELD_STYLES['cwd']}"
    assert spans["a/branch"] == f"bold {FIELD_STYLES['branch']}"


def test_a_card_spends_one_column_on_its_gutter():
    """A sidebar is mostly gutter otherwise: the table adds no padding of its
    own, so what the card writes is the whole left margin."""
    cells = [Text("15:24"), Text(""), Text("CC"), Text("n"), Text(""), Text("~/w"), Text("m")]
    (body,) = app._as_card(cells, 40)

    assert app._CARD_CELL_PADDING == 0
    assert body.plain.split("\n")[1].startswith(" 15:24")
    assert not body.plain.split("\n")[1].startswith("  ")


def test_the_backend_label_sits_against_the_right_edge():
    """Labels differ in width ("CC", "cx"), and it is the edge they share."""
    cells = [Text("15:24"), Text(""), Text("cx"), Text("n"), Text(""), Text(""), Text("m")]
    (body,) = app._as_card(cells, 40)

    assert body.plain.split("\n")[0].endswith("cx")
    assert len(body.plain.split("\n")[0]) == 40


def test_the_message_uses_width_that_only_the_header_label_needs():
    cells = [
        Text("15:24"),
        Text(""),
        Text("Opus 5.5"),
        Text("n"),
        Text(""),
        Text(""),
        Text("x" * 39),
    ]
    (body,) = app._as_card(cells, 40, message_lines=2)

    lines = body.plain.split("\n")
    assert lines[0].endswith("Opus 5.5")
    assert lines[2] == " " + "x" * 39
    assert lines[3] == ""


def test_bar_mode_uses_yellow_for_the_title_and_provider_colour_for_the_model():
    backend = backend_indicators.backend_text(
        "claude:session", {}, True, model="claude-opus-5-5"
    )
    cells = [
        Text("15:24"),
        Text("●"),
        backend,
        jump_gutter(0) + styled_cell("a name", True, "name"),
        Text(""),
        Text(""),
        Text("message"),
    ]
    (body,) = app._as_card(cells, 40, gutter_width=2, unread_style="bar")
    headline = body.plain.split("\n")[0]
    console = Console(color_system="truecolor")

    assert "●" not in headline
    assert headline.endswith(" ")
    model_start = headline.index("Opus 5.5")
    assert body.get_style_at_offset(console, 0).bgcolor.name == ATTENTION_COLOR
    assert body.get_style_at_offset(console, model_start - 1).bgcolor.name == "#d88760"
    assert body.get_style_at_offset(console, model_start).color.name == "#000000"
    assert body.get_style_at_offset(console, 0).color.name == "#000000"
    assert body.get_style_at_offset(
        console, model_start + len("Opus 5.5")
    ).bgcolor.name == "#d88760"


def test_bar_mode_does_not_paint_over_the_selected_green_edge():
    cells = [
        Text("15:24"),
        Text("●"),
        backend_indicators.backend_text("codex:session", {}, True, model="gpt-5.6-sol"),
        jump_gutter(0, True) + styled_cell("a name", True, "name"),
        Text(""),
        Text(""),
        Text("message"),
    ]
    (body,) = app._as_card(cells, 40, gutter_width=2, unread_style="bar")
    console = Console(color_system="truecolor")

    assert body.plain.startswith(HERE_BAR)
    assert body.get_style_at_offset(console, 0).bgcolor is None
    assert body.get_style_at_offset(console, 1).bgcolor.name == ATTENTION_COLOR


def test_bar_mode_hides_the_empty_card_header():
    class Table:
        id = "main_table"
        columns = {}
        cursor_type = ""
        cell_padding = -1
        show_header = True

        def add_column(self, *_args, **_kwargs):
            pass

    pane = app.LemonaidApp()
    pane.config.tui.card_unread_style = "bar"
    table = Table()

    pane._setup_table(table, width=58, height=89)

    assert not table.show_header


def test_a_known_model_does_not_flicker_back_to_the_backend_fallback():
    tui = app.LemonaidApp()
    known = db.Notification(
        id=1,
        channel="claude:abc",
        message="working",
        metadata={"model_provider": "anthropic", "model": "claude-opus-5-5"},
    )
    temporarily_missing = db.Notification(
        id=1,
        channel="claude:abc",
        message="working",
    )

    assert tui._backend_value(known, False).plain == "Opus 5.5"
    assert tui._backend_value(temporarily_missing, False).plain == "Opus 5.5"


def test_building_a_card_does_not_mutate_column_layout_justification():
    cells = [Text("15:24"), Text(""), Text("CC"), Text("n"), Text(""), Text(""), Text("m")]
    cells[app._BACKEND_CELL].justify = "right"
    app._as_card(cells, 40)

    assert cells[app._BACKEND_CELL].justify == "right"


def test_the_marker_does_not_share_the_name_colour():
    """Sharing it made the dot read as the first glyph of the name."""
    assert app.UNREAD_MARKER_STYLE != f"bold {app.FIELD_STYLES['name']}"


def test_a_long_message_uses_every_line_it_is_given():
    """A tall pane's whole point: the message stops being cut mid-sentence."""
    cells = [
        Text("15:24"),
        Text(""),
        Text("CC"),
        Text("n"),
        Text(""),
        Text("~/w"),
        Text(" ".join(f"word{i}" for i in range(200))),
    ]

    (short,) = app._as_card(list(cells), 40, message_lines=3)
    (tall,) = app._as_card(list(cells), 40, message_lines=12)

    assert len(short.plain.split("\n")) == 3 + 3  # name, context, budget, separator-ish
    assert len(tall.plain.split("\n")) == 3 + 12


def _card_columns(width: int, height: int) -> tuple[list[int], int, bool]:
    """Column widths, the width DataTable will report, and whether it h-scrolls."""

    async def run():
        pane = app.LemonaidApp()
        async with pane.run_test(size=(width, height)) as pilot:
            await pilot.pause()
            await pilot.pause()
            table = pane.query_one("#main_table")
            return (
                [c.width for c in table.columns.values()],
                sum(c.get_render_width(table) for c in table.columns.values()),
                table.show_horizontal_scrollbar,
            )

    return asyncio.run(run())


def test_a_card_row_reaches_the_edge_of_the_pane():
    """One column short and the backend label floats off the right edge."""
    widths, rendered, hbar = _card_columns(58, 30)

    assert len(widths) == 1
    assert widths[app._CARD_BODY_COLUMN] == rendered
    # Everything but the scrollbar's one reserved column.
    assert rendered == 58 - 1
    assert not hbar


def test_a_card_row_still_fits_when_the_pane_is_tiny():
    """The body has a floor, so a very narrow pane overflows rather than
    rendering a negative width - but it must not do so silently at usual sizes."""
    for width in (40, 45, 50, 58, 64, 70):
        _widths, rendered, hbar = _card_columns(width, 30)
        assert not hbar, width
        assert rendered == width - 1, width


def _layout(width: int, height: int) -> str:
    """Which layout a pane of this size gets, without building an app."""
    if width < app._SIDEBAR_COLS:
        return "cards"

    return "cards" if height >= width * app._CARD_ASPECT else "columns"


def test_a_narrow_pane_gets_cards_at_any_height():
    """The scratch pane keeps its width and changes height with the window it
    joins; deciding on aspect alone made it flip layout on a window switch."""
    assert _layout(58, 89) == "cards"
    assert _layout(58, 58) == "cards"
    assert _layout(58, 24) == "cards"


def test_a_wide_short_pane_still_gets_columns():
    assert _layout(145, 40) == "columns"
    assert _layout(200, 58) == "columns"


def test_a_wide_but_tall_pane_still_gets_cards():
    assert _layout(100, 130) == "cards"


def test_a_scratch_pane_on_the_left_is_cards_whatever_its_size(monkeypatch, tmp_path):
    """A sidebar by declaration: a moment at 245 columns mid-relayout, or a short
    window, must not turn it into a top pane."""
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    scratch.set_position("left")
    sidebar = app.LemonaidApp(scratch_mode=True)

    assert sidebar._cards(58, 89)
    assert sidebar._cards(245, 16)
    assert sidebar._cards(245, 89)


def test_a_scratch_pane_on_top_is_columns_whatever_its_size(monkeypatch, tmp_path):
    monkeypatch.setattr(scratch, "get_state_path", lambda: tmp_path)
    scratch.set_position("top")
    strip = app.LemonaidApp(scratch_mode=True)

    assert not strip._cards(245, 16)
    assert not strip._cards(58, 89)


def test_a_plain_lma_still_decides_from_its_shape():
    assert app.LemonaidApp()._cards(58, 89)
    assert not app.LemonaidApp()._cards(245, 16)


def test_a_read_card_emits_no_bold_at_all():
    """Bold on the marker slot would bleed into the name beside it.

    A colour change does not clear the bold attribute - only a reset does - so a
    bold placeholder in the empty marker slot puts every following field on the
    terminal's bold face, whatever the app thinks it asked for. The rendered
    attributes are the thing to assert on; the source styles look right either way.
    """
    cells = [
        styled_cell("15:24", False, "time"),
        Text(""),  # read: no dot
        styled_cell("CC", False, "backend"),
        styled_cell("a-name", False, "name"),
        styled_cell("", False, "branch"),
        styled_cell("~/w/repo", False, "cwd"),
        styled_cell("a message", False, "message"),
    ]
    (body,) = app._as_card(cells, 60)

    assert not any("bold" in str(span.style) for span in body.spans)


def test_an_unread_card_bolds_the_dot_but_not_the_message():
    cells = [
        styled_cell("15:24", True, "time"),
        Text("●"),
        styled_cell("CC", True, "backend"),
        styled_cell("a-name", True, "name"),
        styled_cell("", True, "branch"),
        styled_cell("~/w/repo", True, "cwd"),
        styled_cell("a message", True, "message"),
    ]
    (body,) = app._as_card(cells, 60)
    styles = {body.plain[s.start : s.end]: str(s.style) for s in body.spans}

    assert "bold" in styles["a-name"], "an unread name is bold"
    assert "bold" not in styles["a message"], "the message reads as prose, never bold"
