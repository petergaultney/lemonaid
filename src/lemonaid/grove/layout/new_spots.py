"""Ground for a tree new to its block, or one moving off crowded ground."""

import dataclasses
import math
from typing import Any

from ..draw import trees
from ..model import Plot, Tree
from . import labels, placement, sizes

_DAY = 86400


def units_wide(shape: trees.Shape) -> int:
    """A tree's width in grove units: its crown, or its tag, which is drawn the same number of
    cells wide at any zoom.
    """
    return max(round(2 * shape.rx) + 2, round(shape.width / sizes.CELLS_PER_UNIT))


def new_spot(
    tree: Tree,
    label: str,
    size: float,
    plot: Plot,
    spots: dict[str, Any],
    now: float,
    reuse: bool = True,
    toward: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """A spot for a tree new to the block: the oldest free spot, unless not *reuse*, else
    the free ground nearest *toward* that placement finds.
    """
    taken = {
        s["letter"]
        for s in spots.values()
        if not s.get("gone_since") or now - s["gone_since"] < _DAY
    }
    letter = labels.pick_letter(label, taken)
    free = sorted((s for s in spots.values() if s.get("gone_since")), key=lambda s: s["gone_since"])
    if free and reuse:
        oldest = next(k for k, s in spots.items() if s is free[0])
        reused = spots.pop(oldest)
        return {"x": reused["x"], "y": reused["y"], "letter": letter, "gone_since": None}

    shape = trees.shape(dataclasses.replace(tree, label=label), letter, size)
    width = units_wide(shape)
    height, top = (math.ceil(rows / sizes.ROWS_PER_UNIT) for rows in (shape.height, shape.top))
    placed = [
        (
            s["x"] - s.get("w", width) // 2,
            s["y"] - s.get("top", top),
            s.get("w", width),
            s.get("h", height),
        )
        for s in spots.values()
        if "x" in s  # not one waiting to stand afresh
    ]
    x, y = placement.new_spot(plot, (width, height), placed, toward)
    return {
        "x": x + width // 2,
        "y": y + top,
        "w": width,
        "h": height,
        "top": top,
        "letter": letter,
        "gone_since": None,
    }
