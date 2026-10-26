"""A grid of terminal cells to draw the grove into, and its conversion to text."""

import dataclasses
import functools
from collections import abc

from rich.segment import Segment
from rich.style import Style

BACKGROUND = "#0b0e13"
# Quadrant block characters indexed by bits: 1 top-left, 2 top-right, 4 bottom-left, 8 bottom-right.
QUADRANTS = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"


@dataclasses.dataclass
class Cell:
    char: str = " "
    fg: str = "#e6ebf2"
    bg: str = ""
    bold: bool = False
    underline: bool = False
    target: tuple[str, ...] = ()  # what a click here selects: (digit,) or (digit, letter)
    link: str = ""  # a URL the terminal opens, as the inbox links PR numbers


@dataclasses.dataclass
class Canvas:
    width: int
    height: int
    rows: list[list[Cell]]
    dim: float = 0.0  # blend everything drawn toward the background by this much
    target: tuple[str, ...] = ()


def blank(width: int, height: int) -> Canvas:
    return Canvas(
        width, height, [[Cell(bg=BACKGROUND) for _ in range(width)] for _ in range(height)]
    )


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


@functools.lru_cache(maxsize=8192)
def mix(color: str, toward: str, amount: float) -> str:
    if amount <= 0:
        return color

    a, b = _rgb(color), _rgb(toward)
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b, strict=True))


def bg_at(canvas: Canvas, x: int, y: int) -> str:
    if 0 <= x < canvas.width and 0 <= y < canvas.height:
        return canvas.rows[y][x].bg

    return BACKGROUND


def put(
    canvas: Canvas,
    x: float,
    y: float,
    char: str,
    fg: str,
    bg: str | None = None,
    bold: bool = False,
    underline: bool = False,
    link: str = "",
) -> None:
    """Draw one cell. A *bg* of None keeps the background already there."""
    col, row = round(x), round(y)
    if not (0 <= col < canvas.width and 0 <= row < canvas.height):
        return

    cell = canvas.rows[row][col]
    cell.char = char
    cell.fg = mix(fg, BACKGROUND, canvas.dim)
    if bg is not None:
        cell.bg = mix(bg, BACKGROUND, canvas.dim) if bg else ""
    cell.bold = bold
    cell.link = link
    cell.underline = underline
    if canvas.target:
        cell.target = canvas.target


def wide(canvas: Canvas, x: float, y: float, char: str, fg: str, bg: str | None = None) -> None:
    """A character two cells wide, such as an emoji: it takes this cell, and the next draws nothing."""
    put(canvas, x, y, char, fg, bg)
    put(canvas, x + 1, y, "", fg, bg)


def text(
    canvas: Canvas,
    x: float,
    y: float,
    s: str,
    fg: str,
    bg: str | None = None,
    bold: bool = False,
    limit: int = 999,
    underline: bool = False,
    link: str = "",
) -> None:
    for i, char in enumerate(s[: max(0, limit)]):
        put(canvas, x + i, y, char, fg, bg, bold, underline, link)


def fill(canvas: Canvas, x: int, y: int, w: int, h: int, bg: str) -> None:
    for row in range(y, y + h):
        for col in range(x, x + w):
            put(canvas, col, row, " ", bg, bg)


ROUND = ("╭", "╮", "╰", "╯", "─", "│")
DOUBLE = ("╔", "╗", "╚", "╝", "═", "║")


def box(
    canvas: Canvas, x: int, y: int, w: int, h: int, fg: str, style: abc.Sequence[str] = ROUND
) -> None:
    tl, tr, bl, br, horizontal, vertical = style
    for col in range(x + 1, x + w - 1):
        put(canvas, col, y, horizontal, fg)
        put(canvas, col, y + h - 1, horizontal, fg)
    for row in range(y + 1, y + h - 1):
        put(canvas, x, row, vertical, fg)
        put(canvas, x + w - 1, row, vertical, fg)
    for col, row, char in (
        (x, y, tl),
        (x + w - 1, y, tr),
        (x, y + h - 1, bl),
        (x + w - 1, y + h - 1, br),
    ):
        put(canvas, col, row, char, fg)


@functools.lru_cache(maxsize=4096)
def _style(fg: str, bg: str, bold: bool, underline: bool, link: str) -> Style:
    return Style(color=fg, bgcolor=bg or None, bold=bold, underline=underline, link=link or None)


def line_segments(row: abc.Sequence[Cell]) -> list[Segment]:
    segments: list[Segment] = []
    run: list[str] = []
    key: tuple[str, str, bool, bool, str] | None = None
    for cell in row:
        cell_key = (cell.fg, cell.bg, cell.bold, cell.underline, cell.link)
        if cell_key != key and run:
            segments.append(Segment("".join(run), _style(*key)))  # type: ignore[misc]
            run = []
        key = cell_key
        run.append(cell.char)
    if run and key:
        segments.append(Segment("".join(run), _style(*key)))

    return segments


def plain_lines(canvas: Canvas) -> list[str]:
    return ["".join(cell.char for cell in row).rstrip() for row in canvas.rows]
