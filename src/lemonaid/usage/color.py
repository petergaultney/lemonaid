"""Two color scales for the usage summary.

Pace is usage so far divided by the share of the window elapsed. 1.0 is exactly on pace. Ratios
are multiplicative (twice as fast and half as fast are equally far from on pace), so the pace
colors are placed on a log scale. The configured ratios are where the color is green, yellow,
orange and red; on pace falls between green and yellow. Past red the color slides on to magenta,
fully reached 1.2 times the red ratio, for "too late to fix". Below green, cyan and blue sit as far
under it as orange and red sit over it, so running far under the allowance (waste) reads as blue.

Used share is its own linear 0-100% ramp, purple through blue, green, yellow and orange to red
exactly at 100%. Pace reaches red at its own ratio, and the two measure different things.

The projection is the usage expected at reset, from 0 to 100% of the cap, on a linear scale. Red
means reaching or passing the cap, so anything less says how close the window is expected to come.
"""

import itertools
import math
from collections.abc import Sequence

from . import pace, samples, settings

_RGB = tuple[int, int, int]

_BLUE = (60, 120, 255)
_CYAN = (0, 200, 220)
_GREEN = (0, 200, 100)
_YELLOW = (255, 220, 0)
_ORANGE = (255, 140, 0)
_RED = (255, 50, 40)
_RESET = "\033[0m"

_MAGENTA = (255, 0, 200)
_PURPLE = (130, 90, 220)
_USED_COLORS = (_PURPLE, _BLUE, _GREEN, _YELLOW, _ORANGE, _RED)
_MAGENTA_AFTER_RED = 1.2  # the ratio multiple past red where the color is fully magenta

_PROJECTION_STOPS = [
    (0, _BLUE),
    (30, _CYAN),
    (55, _GREEN),
    (75, _YELLOW),
    (90, _ORANGE),
    (100, _RED),
]


def pace_ratio(s: samples.Sample, now: float, config: settings.UsageConfig) -> float | None:
    """None while too little of the window has elapsed for the ratio to mean anything."""
    elapsed = pace.elapsed_percent(s, now)
    if elapsed < config.pace_min_elapsed_percent:
        return None

    return s.used_percent / elapsed


def _pace_stops(ratios: tuple[float, float, float, float]) -> Sequence[tuple[float, _RGB]]:
    green, yellow, orange, red = (math.log(r) for r in ratios)

    return [
        (2 * green - red, _BLUE),
        (2 * green - orange, _CYAN),
        (green, _GREEN),
        (yellow, _YELLOW),
        (orange, _ORANGE),
        (red, _RED),
        (red + math.log(_MAGENTA_AFTER_RED), _MAGENTA),
    ]


def _interpolate(x: float, stops: Sequence[tuple[float, _RGB]]) -> _RGB:
    if x <= stops[0][0]:
        return stops[0][1]

    for (x1, c1), (x2, c2) in itertools.pairwise(stops):
        if x <= x2:
            t = (x - x1) / (x2 - x1)

            return (
                round(c1[0] + t * (c2[0] - c1[0])),
                round(c1[1] + t * (c2[1] - c1[1])),
                round(c1[2] + t * (c2[2] - c1[2])),
            )

    return stops[-1][1]


def pace_rgb(ratio: float, ratios: tuple[float, float, float, float]) -> _RGB:
    return _interpolate(math.log(max(ratio, 1e-9)), _pace_stops(ratios))


def used_rgb(percent: float) -> _RGB:
    """Linear 0-100%: purple, blue, green, yellow, orange, and red exactly at 100%."""
    return _interpolate(percent, list(zip(range(0, 101, 20), _USED_COLORS, strict=True)))


def projection_rgb(percent: float) -> _RGB:
    return _interpolate(percent, _PROJECTION_STOPS)


def paint(text: str, rgb: _RGB | None) -> str:
    """Dim when there is no color, because there was too little data to judge."""
    if rgb is None:
        return f"\033[2m{text}{_RESET}"

    r, g, b = rgb

    return f"\033[38;2;{r};{g};{b}m{text}{_RESET}"
