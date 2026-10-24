"""Ground for a tree new to its block, or one moving off crowded ground."""

import dataclasses
import math
from collections import abc
from typing import Any

from ..draw import trees
from ..model import Plot, Tree
from . import labels, placement, sizes

_DAY = 86400
_PENNANT_ROWS = 2  # a lead's pennant flies this far above its crown


def units_wide(shape: trees.Shape) -> int:
    """A tree's width in grove units: its crown, or its tag, which is drawn the same number of
    cells wide at any zoom.
    """
    return max(round(2 * shape.rx) + 2, round(shape.width / sizes.CELLS_PER_UNIT))


def footprint(tree: Tree, label: str, letter: str, size: float) -> tuple[int, int, int]:
    """The ground a tree and its tag cover: width and height in grove units, and units from the
    top to the crown's center. A lead's includes its pennant.
    """
    shape = trees.shape(dataclasses.replace(tree, label=label), letter, size)
    flag = _PENNANT_ROWS if tree.lead else 0
    height, top = (
        math.ceil((rows + flag) / sizes.ROWS_PER_UNIT) for rows in (shape.height, shape.top)
    )
    return units_wide(shape), height, top


def _on_ground(
    tree: Tree,
    label: str,
    letter: str,
    size: float,
    spots: dict[str, Any],
    place: abc.Callable[
        [list[placement.Size], list[placement.Rect]],
        tuple[tuple[int, int], placement.Size] | None,
    ],
) -> dict[str, Any] | None:
    # Its own size if there's room for it, else its smallest, which spacing then shrinks it to.
    footprints = [footprint(tree, label, letter, at) for at in (size, sizes.SMALLEST)]
    width, height, top = footprints[0]
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
    found = place(footprints, placed)
    if found is None:
        return None

    (x, y), fitted = found
    width, height, top = fitted
    return {
        "x": x + width // 2,
        "y": y + top,
        "w": width,
        "h": height,
        "top": top,
        "letter": letter,
        "gone_since": None,
    }


def new_spot(
    tree: Tree,
    label: str,
    size: float,
    plot: Plot,
    spots: dict[str, Any],
    now: float,
    reuse: bool = True,
    toward: tuple[float, float] | None = None,
    squeeze: bool = False,
) -> dict[str, Any]:
    """A spot for a tree new to the block: the oldest free spot, unless not *reuse*, else
    the free ground nearest *toward* that placement finds, else past the plot's edge or, with
    *squeeze*, in over the others (see `placement.new_spot`).
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

    spot = _on_ground(
        tree,
        label,
        letter,
        size,
        spots,
        lambda fits, placed: placement.new_spot(plot, fits, placed, toward, squeeze),
    )
    assert spot is not None  # placement.new_spot always finds one
    return {**spot, "squeezed": True} if squeeze else spot


def clear_spot(
    tree: Tree, label: str, letter: str, size: float, plot: Plot, spots: dict[str, Any]
) -> dict[str, Any] | None:
    """Free ground for a tree standing on another's, or None when its block has none left."""
    return _on_ground(
        tree,
        label,
        letter,
        size,
        spots,
        lambda fits, placed: placement.first_room(plot, fits, placed),
    )
