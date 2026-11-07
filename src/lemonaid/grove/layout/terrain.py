"""The ground the roads and the stream cover, which no block but the packhouse stands on.

An end of a road or the stream on the world's right or bottom border runs on past it, as the
grove draws it out to the map's edge however far blocks reach.
"""

import functools
import itertools
import math
from collections import abc
from typing import Any

from ..draw.ground import inside
from ..model import WORLD_HEIGHT, WORLD_WIDTH, Plot
from . import landmarks, placement

Line = tuple[tuple[int, int], ...]
# Grove columns each row's roads and stream cover, as [start, end) runs, by row.
Covered = dict[int, tuple[tuple[int, int], ...]]
_PLOT_KEYS = ("x", "y", "w", "h", "roundness", "seed", "texture")
# Grove columns and rows kept clear between a block and any road or the stream: a row is about
# twice as tall as a column is wide, so one row looks as wide a gap as two columns.
GAP = (2, 1)
_FAR = 10  # times the world's size, how far an end on its border runs on


def _segment(a: tuple[float, float], b: tuple[float, float]) -> abc.Iterator[tuple[int, int]]:
    steps = max(1, round(2 * max(abs(b[0] - a[0]), abs(b[1] - a[1]))))
    for k in range(steps + 1):
        yield (
            math.floor(a[0] + (b[0] - a[0]) * k / steps),
            math.floor(a[1] + (b[1] - a[1]) * k / steps),
        )


def _end(inner: tuple[int, int], end: tuple[int, int]) -> abc.Iterator[tuple[int, int]]:
    """The last segment, from *inner* to *end*, wherever it is drawn: an end on the world's right
    or bottom border is drawn out to the grove's extent, any distance up to `_FAR` worlds away,
    which swings the whole segment. Every line it can take is between the two extremes.
    """
    far = (
        end[0] * _FAR if end[0] >= WORLD_WIDTH else end[0],
        end[1] * _FAR if end[1] >= WORLD_HEIGHT else end[1],
    )
    if far == end:
        yield from _segment(inner, end)
        return

    yield from _segment(inner, far)
    # Fill from the nearest line, and on from the end along the border's own row or column, to
    # the farthest line.
    for x, y in itertools.chain(_segment(inner, end), _segment(end, far)):
        across = (x, inner[1] + (far[1] - inner[1]) * (x - inner[0]) / max(1, far[0] - inner[0]))
        down = (inner[0] + (far[0] - inner[0]) * (y - inner[1]) / max(1, far[1] - inner[1]), y)
        yield from _segment((x, y), across if far[0] != end[0] else down)


def _cells(points: Line, above: int, below: int, columns: int) -> abc.Iterator[tuple[int, int]]:
    """Grove cells within *columns* either side of the line through *points*, from *above* rows
    over it to *below* rows under it.
    """
    last = len(points) - 2
    path = itertools.chain(
        *(
            itertools.chain(
                _end(b, a) if i == 0 else _segment(a, b), _end(a, b) if i == last else ()
            )
            for i, (a, b) in enumerate(itertools.pairwise(points))
        )
    )
    for x, y in path:
        for dy in range(-above, below + 1):
            yield from ((x + dx, y + dy) for dx in range(-columns, columns + 1))


def _runs(cells: abc.Iterable[tuple[int, int]]) -> Covered:
    columns: dict[int, set[int]] = {}
    for x, y in cells:
        columns.setdefault(y, set()).add(x)
    runs: Covered = {}
    for y, xs in columns.items():
        ordered = sorted(xs)
        starts = [x for i, x in enumerate(ordered) if i == 0 or ordered[i - 1] != x - 1]
        ends = [
            x + 1 for i, x in enumerate(ordered) if i == len(ordered) - 1 or ordered[i + 1] != x + 1
        ]
        runs[y] = tuple(zip(starts, ends, strict=True))
    return runs


@functools.lru_cache(maxsize=8)
def covered(roads: tuple[Line, ...], stream: Line) -> Covered:
    """The ground the roads and stream are drawn over at any zoom the grove view draws, once
    rounded to screen cells: what new blocks are laid out clear of.
    """
    return _runs(
        itertools.chain(*(_cells(road, 1, 1, 1) for road in roads), _cells(stream, 1, 2, 1))
    )


@functools.lru_cache(maxsize=8)
def under(roads: tuple[Line, ...], stream: Line) -> Covered:
    """The ground right under the roads and stream, with no room for rounding: a block whose
    edge only comes close to them at some zoom isn't on them.
    """
    return _runs(
        itertools.chain(*(_cells(road, 0, 0, 0) for road in roads), _cells(stream, 0, 0, 0))
    )


def lines(saved: dict[str, Any]) -> tuple[tuple[Line, ...], Line]:
    """The saved layout's roads and stream, or the defaults for a layout laid before them."""
    roads = saved["roads"] if "roads" in saved else landmarks.default_roads()
    stream = saved["stream"] if "stream" in saved else landmarks.default_stream()
    return tuple(tuple((x, y) for x, y in road) for road in roads), tuple((x, y) for x, y in stream)


def of_saved(saved: dict[str, Any]) -> Covered:
    return covered(*lines(saved))


def crosses_box(ground: Covered, rect: placement.Rect, gap: tuple[int, int] = (0, 0)) -> bool:
    """Whether *rect*, and *gap* columns and rows around it, take in any covered cell."""
    x, y, w, h = rect
    across, down = gap
    return any(
        start < x + w + across and x - across < end
        for row in range(y - down, y + h + down)
        for start, end in ground.get(row, ())
    )


def crosses(ground: Covered, plot: Plot) -> bool:
    """Whether a road or the stream runs over *plot*'s ground, not just its box's corners."""
    return any(
        inside(plot, cx + 0.5, row + 0.5)
        for row in range(plot.y, plot.y + plot.h)
        for start, end in ground.get(row, ())
        for cx in range(max(start, plot.x), min(end, plot.x + plot.w))
    )


def crosses_saved(saved: dict[str, Any], data: dict[str, Any]) -> bool:
    """Whether a road or the stream runs right under saved plot *data*, but for the
    packhouse's.
    """
    return data.get("texture") != "house" and crosses(
        under(*lines(saved)), Plot(**{k: data[k] for k in _PLOT_KEYS})
    )


def _near(ground: Covered, data: dict[str, Any]) -> bool:
    """Whether saved plot *data*, but for the packhouse's, is within `GAP` of *ground*."""
    return data.get("texture") != "house" and crosses_box(
        ground, (data["x"], data["y"], data["w"], data["h"]), GAP
    )


def _clear_box(ground: Covered, rect: placement.Rect) -> placement.Rect:
    """The largest box inside *rect* that is `GAP` clear of every road and stream."""
    x, y, w, h = rect
    heights = [0] * w
    best = (x, y, 0, 0)
    for row in range(y, y + h):
        heights = [
            0 if crosses_box(ground, (x + i, row, 1, 1), GAP) else heights[i] + 1 for i in range(w)
        ]
        for i in range(w):
            least = heights[i]
            for j in range(i, w):
                least = min(least, heights[j])
                if least * (j - i + 1) > best[2] * best[3]:
                    best = (x + i, row - least + 1, j - i + 1, least)
    return best


def move_off(saved: dict[str, Any], ground: Covered) -> None:
    """Take every block saved over a road or the stream off it, once: trimmed to the part
    clear of *ground* when that keeps half its ground, else moved whole to the nearest free
    ground. Its trees keep their place on the ground, and any the trim cuts off stand afresh
    inside. Open ground over them is forgotten. A block checked is marked `clear` with the gap
    it was checked for and never checked again, so one moved or resized close to them stays
    where it was put.
    """
    plots = saved["plots"]
    for name in sorted(plots):
        data = plots[name]
        if data.get("clear") == list(GAP):
            continue

        if not _near(ground, data):
            data["clear"] = list(GAP) if data.get("open_since") is None else 0
            continue

        if data.get("open_since") is not None:
            del plots[name]
            saved["trees"].pop(name, None)
            continue

        old = (data["x"], data["y"], data["w"], data["h"])
        x, y, w, h = _clear_box(ground, old)
        trimmed = 2 * w * h >= old[2] * old[3] and w >= 12 and h >= 5
        if not trimmed:
            taken = [(d["x"], d["y"], d["w"], d["h"]) for key, d in plots.items() if key != name]
            found = placement.new_plot(
                name, old[2:], taken, functools.partial(crosses_box, ground, gap=GAP)
            )
            x, y, w, h = found.x, found.y, old[2], old[3]
        data.update(x=x, y=y, w=w, h=h)
        spots = saved["trees"].get(name, {})
        for key, spot in list(spots.items()):
            if "x" not in spot:
                continue
            spot["x"], spot["y"] = spot["x"] + old[0] - x, spot["y"] + old[1] - y
            if spot.get("gone_since") and not (0 <= spot["x"] <= w and 0 <= spot["y"] <= h):
                del spots[key]  # a bare tree the trim cut off
        if trimmed:
            data.pop("crowd", None)  # its trees sized afresh for the ground left
        data["clear"] = list(GAP)
