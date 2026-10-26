"""A plot's ground drawn onto the screen at some scale, with its signpost."""

import dataclasses
import functools
import itertools
from collections import abc

from ..model import Plot
from . import colors, crown
from .canvas import BACKGROUND, Canvas, mix, put, text
from .ground import inside, noise, texture


@dataclasses.dataclass(frozen=True)
class View:
    """Grove point (x, y) is drawn at screen ((x - left) * sx + ox, (y - top) * sy + oy)."""

    left: float
    top: float
    sx: float
    sy: float
    ox: int = 0
    oy: int = 1

    def screen(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.left) * self.sx + self.ox, (y - self.top) * self.sy + self.oy

    def world(self, col: float, row: float) -> tuple[float, float]:
        return (col - self.ox) / self.sx + self.left, (row - self.oy) / self.sy + self.top


@functools.lru_cache(maxsize=4)
def _specks(width: int, height: int) -> tuple[tuple[int, int], ...]:
    return tuple(
        (x, y) for y in range(1, height - 1) for x in range(width) if noise(x, y * 7) < 0.012
    )


def speckle(canvas: Canvas) -> None:
    for x, y in _specks(canvas.width, canvas.height):
        put(canvas, x, y, "·", "#20262f")


@functools.lru_cache(maxsize=64)
def _ground_cells(
    plot: Plot, view: View, color: str, live: bool
) -> tuple[tuple[int, int, str, str, str], ...]:
    """(column, row, char, fg, bg) for each cell of *plot*'s ground: the same for every frame
    drawn at one view, so a key that only moves a choice doesn't work them out again.
    """
    x0, y0 = view.screen(plot.x, plot.y)
    x1, y1 = view.screen(plot.x + plot.w, plot.y + plot.h)
    soil = mix(color, BACKGROUND, 0.87) if live else "#13161a"
    rim = mix(color, BACKGROUND, 0.68) if live else "#252a31"
    marks = mix(color, BACKGROUND, 0.72) if live else "#2a3029"
    dx, dy = 1 / view.sx, 1 / view.sy
    cells = []
    for row in range(int(y0), int(y1) + 1):
        for col in range(int(x0), int(x1) + 1):
            wx, wy = view.world(col, row)
            if not inside(plot, wx, wy):
                continue
            edge = not all(
                inside(plot, wx + ex, wy + ey) for ex, ey in ((-dx, 0), (dx, 0), (0, -dy), (0, dy))
            )
            if edge:
                cells.append((col, row, "░" if live else "·", rim, soil))
            else:
                cells.append(
                    (
                        col,
                        row,
                        texture(plot, col - int(x0), row - int(y0)) if live else " ",
                        marks,
                        soil,
                    )
                )
    return tuple(cells)


def ground(canvas: Canvas, plot: Plot, view: View, color: str, live: bool) -> None:
    """Fill *plot*'s outline. Open ground (*live* False) is dark and unmarked."""
    for col, row, char, fg, bg in _ground_cells(plot, view, color, live):
        put(canvas, col, row, char, fg, bg)


def sign(
    canvas: Canvas, plot: Plot, view: View, digit: str, name: str, color: str
) -> tuple[int, int, int, int]:
    """Draw the block's sign; return where it is, (x, y, w, h)."""
    x, y = view.screen(plot.x + plot.w * 0.12, plot.y)
    words = f" {digit} {(name or 'no group').upper()} "
    text(canvas, x, max(1, y), words, "#0b0e13", color, bold=True)
    return round(x), max(1, round(y)), len(words), 1


# A tree with no leaves, standing where a tree whose session ended stood: bare branches over the
# trunk a live tree has, its crown's middle on the second row.
_BARE = ("\u259d\u2599 \u2588 \u259f\u2598", "  \u259c\u2588\u259b  ", "   \u2588   ")  # "▝▙ █ ▟▘"
# Bark a little faded, lit and shaded, by crown paint.
_DEAD_BARK = {
    crown.BARK: mix(colors.TRUNK, BACKGROUND, 0.2),
    crown.BARK_SHADE: mix(colors.TRUNK_SHADE, BACKGROUND, 0.2),
}


# A few dead leaves still on a tree whose session ended recently: (column, row, quadrant).
_DEAD_LEAVES = ((1, -1, "\u2597"), (2, -1, "\u2584"), (4, -1, "\u2596"), (2, 0, "\u2598"))
_DEAD_LEAF = "#b8925e"


def stump(canvas: Canvas, x: float, y: float, label: str = "") -> None:
    """A bare tree at (*x*, *y*); with *label*, its tree's name, it went recently, and keeps a few
    dead leaves and its name below it.
    """
    left, top = round(x) - 3, round(y) - 1
    for col, row, char, drawn, back in crown.bare(_BARE, 3.5):
        put(
            canvas,
            left + col,
            top + row,
            char,
            _DEAD_BARK[drawn],
            _DEAD_BARK[back] if back != crown.NONE else None,
        )
    if not label:
        return

    for col, row, char in _DEAD_LEAVES:
        put(canvas, left + col, top + row, char, _DEAD_LEAF)
    name = label if len(label) <= 20 else label[:19] + "\u2026"
    text(
        canvas, round(x) - len(name) // 2, top + len(_BARE), name, mix(_DEAD_LEAF, BACKGROUND, 0.3)
    )


def _along(view: View, points: abc.Sequence[tuple[int, int]]) -> abc.Iterator[tuple[int, int]]:
    """Every screen cell on the polyline through *points*, in order."""
    for (x0, y0), (x1, y1) in itertools.pairwise(points):
        sx0, sy0 = view.screen(x0, y0)
        sx1, sy1 = view.screen(x1, y1)
        steps = max(1, round(max(abs(sx1 - sx0), abs(sy1 - sy0) * 2)))
        for k in range(steps + 1):
            yield round(sx0 + (sx1 - sx0) * k / steps), round(sy0 + (sy1 - sy0) * k / steps)


def stream(canvas: Canvas, view: View, points: abc.Sequence[tuple[int, int]]) -> None:
    for x, y in _along(view, points):
        for dx in (-1, 0, 1):
            for dy in (0, 1):
                ripple = "≈" if (x + dx + 2 * (y + dy)) % 4 == 0 else " "
                put(canvas, x + dx, y + dy, ripple, "#4a86b8", "#123049")


def road(canvas: Canvas, view: View, points: abc.Sequence[tuple[int, int]]) -> None:
    for x, y in _along(view, points):
        for dx in (-1, 0, 1):
            put(canvas, x + dx, y, "·" if noise(x + dx, y) < 0.3 else " ", "#4d4433", "#1b1812")
