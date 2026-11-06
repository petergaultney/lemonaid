"""A plot's outline and the ground texture inside it."""

import functools
import math

from ..model import Plot


def noise(a: int, b: int) -> float:
    """A stable pseudo-random number in [0, 1) for a pair of integers."""
    h = (a * 374761393 + b * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h ^ (h >> 16)) / 4294967296


def word_hash(word: str) -> int:
    h = 7
    for char in word:
        h = (h * 31 + ord(char)) & 0x7FFFFFFF
    return h


def _inset(seed: int, side: int, t: float) -> float:
    """How far one edge of a field sits in from its box, as a fraction of the box's half-size,
    at *t* in [-1, 1] along the edge: a little in, leaning, bowed and rippled, by *seed*.
    """
    lean = (noise(seed, side + 10) - 0.5) * 0.08 * t
    bow = (noise(seed, side + 20) - 0.5) * 0.06 * (1 - t * t)
    ripple = 0.012 * math.sin(t * 5 + seed + side)
    return max(0.0, 0.03 + 0.05 * noise(seed, side) + lean + bow + ripple)


def inside(plot: Plot, x: float, y: float) -> bool:
    """Whether grove point (*x*, *y*) is on *plot*: a field with nearly straight edges inside its
    box, its corners rounded more the lower its roundness.
    """
    hw, hh = plot.w / 2, plot.h / 2
    nx, ny = (x - plot.x - hw + 0.5) / hw, (y - plot.y - hh + 0.5) / hh
    left, right = -1 + _inset(plot.seed, 0, ny), 1 - _inset(plot.seed, 1, ny)
    top, bottom = -1 + _inset(plot.seed, 2, nx), 1 - _inset(plot.seed, 3, nx)
    if not (left <= nx <= right and top <= ny <= bottom):
        return False

    # A cell is about twice as tall as it is wide, so a corner's radius is twice as many columns
    # as rows, and it looks round.
    rows = max(0.0, min(0.9, 1.3 / plot.roundness - 0.1)) * min(hh, hw / 2)
    if rows <= 0:
        return True

    kx, ky = 2 * rows / hw, rows / hh
    dx = max(0.0, left + kx - nx, nx - (right - kx)) / kx
    dy = max(0.0, top + ky - ny, ny - (bottom - ky)) / ky
    return dx * dx + dy * dy <= 1


def texture(plot: Plot, x: int, y: int) -> str:
    """The ground mark at a cell, or " "; *x* and *y* are relative to the plot."""
    match plot.texture:
        case "rows":
            return "·" if y % 3 == 1 and x % 3 == 0 else " "
        case "diag":
            return "/" if (x + 2 * y) % 9 == 0 else " "
        case "wave":
            return "~" if y % 3 == 1 and (x + y) % 4 == 0 else " "
        case "dots":
            return "·" if noise(x * 3 + plot.seed, y) < 0.07 else " "
    return " "


@functools.lru_cache(maxsize=256)
def area(plot: Plot) -> int:
    return sum(
        inside(plot, x, y)
        for y in range(plot.y, plot.y + plot.h)
        for x in range(plot.x, plot.x + plot.w)
    )
