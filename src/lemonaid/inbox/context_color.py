"""A lemon's context use as a color, from blue to red at its threshold, wherever it is shown."""

import itertools

from rich.color import Color

# Percent of the threshold to colour, interpolated between stops. Red is the
# threshold itself; past it the colour keeps going to magenta.
_STOPS = (
    (0, (75, 0, 130)),  # deep purple, which a working lemon is already past
    (15, (50, 130, 255)),  # blue
    (40, (0, 200, 100)),  # green
    (70, (255, 220, 0)),  # yellow
    (100, (255, 60, 30)),  # red
    (130, (255, 0, 255)),  # magenta
)


def color(percent: int) -> Color:
    clamped = max(_STOPS[0][0], min(_STOPS[-1][0], percent))
    for (p1, c1), (p2, c2) in itertools.pairwise(_STOPS):
        if clamped <= p2:
            t = (clamped - p1) / (p2 - p1)
            return Color.from_rgb(*(a + t * (b - a) for a, b in zip(c1, c2, strict=True)))

    return Color.from_rgb(*_STOPS[-1][1])
