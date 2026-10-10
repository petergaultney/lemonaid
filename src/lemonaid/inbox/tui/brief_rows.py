"""Brief status on a one-line column row, matching what a card's headline shows."""

from rich.console import Console
from rich.style import Style
from rich.text import Text

from . import context_reading
from .brief_cards import DOT_STYLES, STATUS_STYLES, CardBrief
from .utils import ATTENTION_COLOR

_CONSOLE = Console()
# Deeper than the attention yellow: blocked rows sort first, right under a header
# that turns that yellow while anything is unread, and the two read as one band.
_BLOCKED_ROW = "#c9a93a"


def _restyled(cell: Text, style: str | Style, start: int = 0) -> Text:
    cell = cell.copy()
    cell.stylize(style, start)
    return cell


def background(brief: CardBrief | None) -> Style | None:
    """The row's fill, which the table paints across every cell and its padding."""
    if brief and brief.shown == "blocked":
        return Style(bgcolor=_BLOCKED_ROW)

    style = STATUS_STYLES.get(brief.shown) if brief else None
    return Style(bgcolor=style.bgcolor) if style else None


def styled(
    cells: list[Text],
    brief: CardBrief | None,
    unread_cell: int,
    backend_cell: int,
    name_cell: int,
    gutter_width: int,
) -> list[Text]:
    """`cells` recoloured for the brief's status, or unchanged without one.

    Under a status fill every field takes the fill's text colour, since
    the field colours were picked for the plain background. The model label
    becomes a badge in its provider colour, as it does on an unread card in bar
    mode, and the gutter keeps its jump digit or green bar. A read `idle` row
    dims, as its card does.
    """
    unread = bool(cells[unread_cell].plain)
    if brief and brief.shown == "idle" and not unread:
        return [
            cell if i == unread_cell else _restyled(cell, "dim") for i, cell in enumerate(cells)
        ]

    style = STATUS_STYLES.get(brief.shown) if brief else None
    if not brief or not style:
        return cells

    def recoloured(index: int, cell: Text) -> Text:
        if index == unread_cell:
            dot = DOT_STYLES.get(brief.shown)
            return _restyled(cell, dot) if dot else cell
        if index == backend_cell:
            reading, model = context_reading.split(cell)
            provider = model.get_style_at_offset(_CONSOLE, 0).color if model.plain else None
            fill = Style(color="#000000", bgcolor=provider or ATTENTION_COLOR)
            badge = _restyled(context_reading.padded_model(reading, model, fill), fill)
            backend = context_reading.filled(reading) + badge
            backend.justify = cell.justify
            return backend

        return _restyled(cell, Style(color=style.color), gutter_width if index == name_cell else 0)

    return [recoloured(index, cell) for index, cell in enumerate(cells)]
