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


def inside(plot: Plot, x: float, y: float) -> bool:
    """Whether grove point (*x*, *y*) is on *plot*: a wobbly superellipse inside its box."""
    cx, cy = plot.x + plot.w / 2 - 0.5, plot.y + plot.h / 2 - 0.5
    nx, ny = (x - cx) / (plot.w / 2), (y - cy) / (plot.h / 2)
    p = plot.roundness
    r = (abs(nx) ** p + abs(ny) ** p) ** (1 / p)
    angle = math.atan2(ny, nx)
    wobble = 0.06 * math.sin(angle * 3 + plot.seed) + 0.04 * math.sin(angle * 5 + plot.seed * 2.3)
    return r <= 1 + wobble - 0.02


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
