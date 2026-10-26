"""A pulsing grove: its picture at rest and at the pulse's darkest, and every frame between.

Everything that pulses mixes its color toward another in proportion to the phase, so a frame
anywhere in the pulse blends the two ends' colors, cell by cell, without drawing the grove again.
"""

import dataclasses
import math
from collections import abc

from ..draw.canvas import Canvas, mix

PERIOD = 3.2  # seconds a pulse takes, from rest to darkest and back
TICK = 1 / 12  # seconds between frames, often enough that the pulse reads as smooth
_STEPS = 64  # phases a pulse is drawn at, so blended colors repeat and stay cached


@dataclasses.dataclass(frozen=True)
class Ends:
    rest: Canvas
    dark: Canvas
    changing: tuple[tuple[int, int], ...]  # (x, y) of every cell whose colors differ


def ends(draw: abc.Callable[[float], Canvas]) -> Ends:
    """The picture *draw* makes at rest and at the pulse's darkest, by phase."""
    rest, dark = draw(0.0), draw(1.0)
    return Ends(
        rest,
        dark,
        tuple(
            (x, y)
            for y, (still, darkest) in enumerate(zip(rest.rows, dark.rows, strict=True))
            for x, (a, b) in enumerate(zip(still, darkest, strict=True))
            if (a.fg, a.bg) != (b.fg, b.bg)
        ),
    )


def phase(now: float) -> float:
    """How far into its darkening the pulse is at *now*, in seconds: 0 at rest, 1 darkest."""
    eased = (1 - math.cos(2 * math.pi * now / PERIOD)) / 2
    return round(eased * _STEPS) / _STEPS


def frame(pulse: Ends, at: float) -> Canvas:
    """The picture *at* a phase between the two ends."""
    if at <= 0 or not pulse.changing:
        return pulse.rest

    rows = [list(row) for row in pulse.rest.rows]
    for x, y in pulse.changing:
        a, b = pulse.rest.rows[y][x], pulse.dark.rows[y][x]
        rows[y][x] = dataclasses.replace(
            a, fg=mix(a.fg, b.fg, at), bg=mix(a.bg, b.bg, at) if a.bg and b.bg else a.bg
        )
    return dataclasses.replace(pulse.rest, rows=rows)
