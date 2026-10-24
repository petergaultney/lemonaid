"""Whether a block's trees stand clear of each other and inside their plot, and more ground for a
block whose trees have spilled out of it.
"""

import dataclasses
from collections import abc
from typing import Any

from ..draw import trees
from ..model import Tree
from . import new_spots, placement


def footprint(tree: Tree, label: str, letter: str, size: float, x: int, y: int) -> placement.Rect:
    """The ground a tree standing at (*x*, *y*) covers, crown and tag."""
    shape = trees.shape(dataclasses.replace(tree, label=label), letter, size)
    width = new_spots.units_wide(shape)
    return x - width // 2, y - shape.top, width, shape.height


def tangled(
    standing: abc.Iterable[tuple[Tree, placement.Rect]],
) -> list[tuple[Tree, placement.Rect]]:
    """The trees in *standing*, oldest first, that stand mostly on an older tree's ground: two
    thirds of the smaller one's covered. Trees that only grow into each other aren't tangled.
    """
    clear: list[placement.Rect] = []
    found = []
    for tree, rect in standing:
        area = rect[2] * rect[3]
        if any(
            placement.overlap_area(rect, [other]) * 3 >= 2 * min(area, other[2] * other[3])
            for other in clear
        ):
            found.append((tree, rect))
            continue

        clear.append(rect)
    return found


def _reach(rect: placement.Rect, others: abc.Sequence[placement.Rect], most: int, side: str) -> int:
    """How far, up to *most*, *rect* can extend on *side* before it meets another block."""
    x, y, w, h = rect
    for step in range(most, 0, -1):
        grown = {
            "right": (x, y, w + step, h),
            "down": (x, y, w, h + step),
            "left": (x - step, y, w + step, h),
            "up": (x, y - step, w, h + step),
        }[side]
        if (
            grown[0] >= 0
            and grown[1] >= 1
            and not any(placement.overlaps(grown, other, 1) for other in others)
        ):
            return step
    return 0


def grow(name: str, plots: dict[str, Any], need: tuple[int, int]) -> tuple[int, int] | None:
    """Give block *name*'s plot more ground for a tree of *need* (w, h), on whichever side has the
    most free before it meets another block. Returns how far its trees' spots, relative to its
    corner, must shift to stay put on the ground, or None when it can't grow by at least 2.
    """
    plot = plots[name]
    rect = (plot["x"], plot["y"], plot["w"], plot["h"])
    others = [
        (d["x"], d["y"], d["w"], d["h"])
        for key, d in plots.items()
        if key != name and d.get("open_since") is None  # open ground can be built over
    ]
    # A tree too tall for the plot needs it taller, one too wide wider; else either will do.
    short = [
        *(("right", "left") if need[0] + 2 > plot["w"] else ()),
        *(("down", "up") if need[1] + 2 > plot["h"] else ()),
    ] or ["right", "down", "left", "up"]
    reach = {
        side: _reach(rect, others, need[0] + 2 if side in ("right", "left") else need[1] + 2, side)
        for side in short
    }
    side = max(reach, key=lambda k: reach[k])
    step = reach[side]
    if step < 2:
        return None

    x, y, w, h = rect
    plot.update(
        x=x - step if side == "left" else x,
        y=y - step if side == "up" else y,
        w=w + step if side in ("right", "left") else w,
        h=h + step if side in ("down", "up") else h,
    )
    grown = (plot["x"], plot["y"], plot["w"], plot["h"])
    for key in [
        key
        for key, d in plots.items()
        if d.get("open_since") is not None
        and placement.overlaps(grown, (d["x"], d["y"], d["w"], d["h"]), 0)
    ]:
        del plots[key]
    return (step if side == "left" else 0, step if side == "up" else 0)
