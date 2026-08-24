"""Rendering a session as a card, for panes shaped tall and narrow.

A card is as tall as its content needs, within a per-field budget, and ends in a
blank line. Padding every card to one height wasted most of a tall pane on blank
rows; the separator is what keeps them legible as separate entries instead.
"""

from rich.text import Text

from lemonaid.inbox.tui import app
from lemonaid.inbox.tui.utils import styled_cell


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
    body, _ = app._as_card(cells, 38, context_lines=3, message_lines=1)

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
    body, backend = app._as_card(cells, 30, message_lines=3)

    # headline + one context line + message + the separator
    assert len(body.plain.split("\n")) <= 1 + 1 + 3 + 1
    assert backend.plain == "CC"


def test_a_card_ends_in_exactly_one_blank_line():
    """Two would read as a gap, none as a run-on into the next card."""
    cells = [Text("15:24"), Text(""), Text("CC"), Text("n"), Text(""), Text(""), Text("m")]
    body, _ = app._as_card(cells, 40)

    assert body.plain.endswith("\n")
    assert not body.plain.endswith("\n\n")


def test_a_wrap_landing_near_the_boundary_adds_no_second_blank():
    """rich pads a wrap to full width; that blank would read as a gap."""
    cells = [Text("15:24"), Text(""), Text("CC"), Text("n"), Text(""), Text(""), Text("a bc def")]
    body, _ = app._as_card(cells, 12, message_lines=3)

    assert not body.plain.endswith("\n\n")


def test_the_row_is_tall_enough_for_the_separator():
    cells = [Text("15:24"), Text(""), Text("CC"), Text("n"), Text(""), Text("~/w"), Text("m " * 40)]
    card = app._as_card(cells, 30, message_lines=3)

    assert app._row_height(card) == len(card[app._CARD_BODY_COLUMN].plain.split("\n"))


def test_a_short_card_does_not_pad_to_the_budget():
    """Padding is what made a tall pane mostly blank rows."""
    cells = [Text("15:24"), Text(""), Text("CC"), Text("n"), Text(""), Text("~/w"), Text("m")]
    body, _ = app._as_card(cells, 40, message_lines=3)

    assert body.plain == "  n\n  15:24 · ~/w\n  m\n"


def test_every_line_fits_the_width():
    cells = [Text("15:24:18"), Text(""), Text("CC")] + [Text("x" * 90)] * 5
    body, _ = app._as_card(cells, 24, message_lines=2)

    assert all(len(line) <= 24 for line in body.plain.split("\n"))


def test_an_unread_card_leads_with_its_marker():
    cells = [Text("15:24:18"), Text("●"), Text("CC"), Text("thing"), Text(""), Text(""), Text("")]
    body, _ = app._as_card(cells, 40)

    assert body.plain.split("\n")[0].startswith("● thing")


def test_a_read_card_keeps_the_name_aligned():
    """The marker column is a space when read, so names line up down the list."""
    cells = [Text("15:24:18"), Text(""), Text("CC"), Text("thing"), Text(""), Text(""), Text("")]
    body, _ = app._as_card(cells, 40)

    assert body.plain.split("\n")[0] == "  thing"


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
    body, _ = app._as_card(cells, 40)

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
    body, _ = app._as_card(cells, 60)

    spans = {body.plain[s.start : s.end]: s.style for s in body.spans}
    assert spans["a-name"] == "bold cyan"
    assert spans["15:24"] == "bold green"
    assert spans["~/w/repo"] == "bold blue"
    assert spans["a/branch"] == "bold magenta"


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

    short, _ = app._as_card(list(cells), 40, message_lines=3)
    tall, _ = app._as_card(list(cells), 40, message_lines=12)

    assert len(short.plain.split("\n")) == 3 + 3  # name, context, budget, separator-ish
    assert len(tall.plain.split("\n")) == 3 + 12
