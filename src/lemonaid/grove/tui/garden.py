"""Gardening the grove with the mouse: moving and resizing blocks, and moving trees."""

import dataclasses
from collections import abc
from typing import Any

from ..draw import canvas, scene_parts
from ..model import Block, Plot
from . import keys
from .frame import Grove, Lists

_EDGE = 1  # cells in from a block's outline that grab its edge rather than the whole block
_SIDES = ("left", "right", "top", "bottom")


@dataclasses.dataclass(frozen=True)
class Drag:
    block: Block
    tree: str  # the dragged tree's key, or "" for the block
    sides: frozenset[str]  # the edges of the block being dragged; none moves the whole block
    start: tuple[int, int]  # where the drag began on the screen
    scale: tuple[float, float]  # screen cells a grove unit, across and down
    moved: tuple[int, int] = (0, 0)  # in grove units
    name: str = ""  # what to type to reach the tree, as 2c, or the block's digit


def _box(plot: Plot, view: scene_parts.View) -> tuple[float, float, float, float]:
    x0, y0 = view.screen(plot.x, plot.y)
    x1, y1 = view.screen(plot.x + plot.w, plot.y + plot.h)
    return x0, y0, x1 - 1, y1 - 1


def _sides(plot: Plot, view: scene_parts.View, col: int, row: int) -> frozenset[str]:
    x0, y0, x1, y1 = _box(plot, view)
    near = {
        "left": abs(col - x0) <= _EDGE,
        "right": abs(col - x1) <= _EDGE,
        "top": abs(row - y0) <= _EDGE,
        "bottom": abs(row - y1) <= _EDGE,
    }
    return frozenset(side for side in _SIDES if near[side])


def _edge(
    blocks: abc.Iterable[Block], arrangement: Any, view: scene_parts.View, col: int, row: int
) -> Block | None:
    """The block whose outline passes within a cell of (*col*, *row*), drawn there or not: an
    outline is rounded, so its corners and much of its rim aren't on its ground.
    """
    for block in blocks:
        x0, y0, x1, y1 = _box(arrangement.plots[block.name], view)
        inside = x0 - _EDGE <= col <= x1 + _EDGE and y0 - _EDGE <= row <= y1 + _EDGE
        if inside and _sides(arrangement.plots[block.name], view, col, row):
            return block
    return None


def grab(
    grove: Grove, where: keys.Where, size: tuple[int, int], at: tuple[int, int], target: tuple
) -> Drag | None:
    if where.search is not None:
        return None

    block = next((b for b in grove.blocks if target and b.digit == target[0]), None)
    if where.block:
        tree = (
            keys.tree_at(block, grove.arrangement, target[1]) if block and len(target) > 1 else None
        )
        if block is None or tree is None or grove.arrangement.plots[block.name].texture == "house":
            return None
        view = scene_parts.block_view(canvas.blank(*size), grove.arrangement, block)
        letter = grove.arrangement.trees[(block.name, tree.key)].letter
        return Drag(block, tree.key, frozenset(), at, (view.sx, view.sy), name=block.digit + letter)

    view = scene_parts.grove_view(size, grove.arrangement, where.pan)
    edged = _edge(grove.blocks, grove.arrangement, view, *at)
    if edged:
        return Drag(
            edged,
            "",
            _sides(grove.arrangement.plots[edged.name], view, *at),
            at,
            (view.sx, view.sy),
        )
    if block is None:
        return None
    return Drag(block, "", frozenset(), at, (view.sx, view.sy))


def follow(drag: Drag, at: tuple[int, int]) -> Drag:
    moved = (
        round((at[0] - drag.start[0]) / drag.scale[0]),
        round((at[1] - drag.start[1]) / drag.scale[1]),
    )
    return dataclasses.replace(drag, moved=moved)


def describe(drag: Drag, problem: str) -> str:
    what = f"tree {drag.name}" if drag.tree else f"block {drag.block.digit}"
    doing = ("resizing " if drag.sides else "moving ") + what
    return f"{doing}: {problem}" if problem else f"{doing} · release to drop · esc puts it back"


def loose(lists: Lists, drag: Drag) -> Lists:
    """*lists* without where the dragged tree's lemon list was, so it is drawn beside the tree."""
    if not drag.tree:
        return lists

    return {
        view: {k: v for k, v in spots.items() if k != drag.tree} for view, spots in lists.items()
    }
