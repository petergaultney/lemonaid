"""Roads as the window draws them: each end on the world's border runs on far past it, and an end that
stops just short of another road meets it, so no road starts or stops in the open.

The saved roads stay as they are; the terminal grove makes the same reach for its border ends itself
(`layout.terrain`).
"""

import itertools
import math
from collections import abc

from ..model import WORLD_HEIGHT, WORLD_WIDTH, Plot

FAR = 400  # grove units past the border, beyond any view
REACH = 8  # how far short of another road an end may stop and still meet it

Point = tuple[float, float]


def _on_border(p: abc.Sequence[float]) -> bool:
    return p[0] <= 0 or p[1] <= 0 or p[0] >= WORLD_WIDTH or p[1] >= WORLD_HEIGHT


def _inside(p: abc.Sequence[float], plot: Plot) -> bool:
    return plot.x <= p[0] <= plot.x + plot.w and plot.y <= p[1] <= plot.y + plot.h


def _nearest(p: abc.Sequence[float], a: abc.Sequence[float], b: abc.Sequence[float]) -> Point:
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1)))
    return a[0] + t * dx, a[1] + t * dy


def _end(
    end: abc.Sequence[float],
    inner: abc.Sequence[float],
    others: abc.Sequence[abc.Sequence[abc.Sequence[float]]],
    houses: abc.Iterable[Plot],
) -> list[Point]:
    """What to add past *end*, the last point of a road whose next point in is *inner*."""
    if _on_border(end):
        dx, dy = end[0] - inner[0], end[1] - inner[1]
        length = math.hypot(dx, dy) or 1
        return [(end[0] + dx / length * FAR, end[1] + dy / length * FAR)]
    if any(_inside(end, house) for house in houses):
        return []  # it runs into the packhouse

    near = [_nearest(end, a, b) for road in others for a, b in itertools.pairwise(road)]
    met = min(near, key=lambda q: math.dist(q, end), default=None)
    return [met] if met is not None and math.dist(met, end) <= REACH else []


def drawn(
    roads: abc.Sequence[abc.Sequence[abc.Sequence[float]]], houses: abc.Iterable[Plot]
) -> list[list[Point]]:
    houses = list(houses)
    out = []
    for i, road in enumerate(roads):
        if len(road) < 2:
            out.append([tuple(p) for p in road])
            continue

        others = [r for j, r in enumerate(roads) if j != i and len(r) > 1]
        start = _end(road[0], road[1], others, houses)
        finish = _end(road[-1], road[-2], others, houses)
        out.append([*reversed(start), *(tuple(p) for p in road), *finish])
    return out
