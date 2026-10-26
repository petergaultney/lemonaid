"""A lemon's inbox card, drawn in a box beside its tree's list in select mode."""

from collections import abc

from rich.cells import cell_len
from rich.color import Color
from rich.console import Console
from rich.terminal_theme import DEFAULT_TERMINAL_THEME
from rich.text import Text

from . import colors, lemon_list
from .canvas import Canvas, box, fill, mix, put, text, wide

WIDTH = lemon_list.WIDTH
INNER = WIDTH - 2  # what the card's lines may fill inside its box
_PANEL = "#121821"
_CONSOLE = Console(color_system="truecolor", width=400)  # only for turning styles into colors

Rect = tuple[int, int, int, int]


def _hex(color: Color | None) -> str:
    if color is None or color.is_default:
        return ""

    return color.get_truecolor(DEFAULT_TERMINAL_THEME).hex


def _line(canvas: Canvas, x: int, y: int, line: Text, limit: int) -> None:
    """*line* in its own colors, over the card's panel, cut at *limit* cells."""
    col = 0
    for segment in line.render(_CONSOLE):
        style = segment.style
        fg = _hex(style.color if style else None) or colors.TEXT
        bg = _hex(style.bgcolor if style else None) or _PANEL
        if style and style.reverse:
            fg, bg = bg, fg
        if style and style.dim:
            fg = mix(fg, bg, 0.45)
        for char in segment.text:
            width = cell_len(char)
            if col + width > limit:
                return
            if width == 2:
                wide(canvas, x + col, y, char, fg, bg)
            elif width == 1:
                put(canvas, x + col, y, char, fg, bg, bool(style and style.bold))
            col += width


def spot(canvas: Canvas, beside: Rect, rows: int) -> tuple[int, int, int]:
    """Where a card *rows* lines tall goes by the list at *beside*: under it or over it, whichever
    has more open screen, and how many of its lines fit there.
    """
    x, y, _, h = beside
    below, above = canvas.height - 1 - (y + h), y - 1  # the title and prompt rows stay clear
    room = max(below, above)
    shown = max(0, min(rows, room - 2))
    top = y + h if below >= above else y - shown - 2
    return min(max(1, x), max(1, canvas.width - WIDTH - 1)), top, shown


def draw(canvas: Canvas, beside: Rect, lines: abc.Sequence[Text], title: str, border: str) -> None:
    """The card for the list at *beside*, as much of it as the screen has room for."""
    x, y, shown = spot(canvas, beside, len(lines))
    if not shown:
        return

    fill(canvas, x, y, WIDTH, shown + 2, _PANEL)
    for row in canvas.rows[y : y + shown + 2]:  # a click on the card reaches nothing under it
        for cell in row[x : x + WIDTH]:
            cell.target = ()
    box(canvas, x, y, WIDTH, shown + 2, border)
    text(canvas, x + 2, y, f" {title} ", border, _PANEL, bold=True, limit=WIDTH - 4)
    for i, line in enumerate(lines[:shown]):
        _line(canvas, x + 1, y + 1 + i, line, INNER)
