"""How big a tree is drawn: young trees are smaller, and so is every tree in a crowded block."""

import math
from collections import abc

from ..draw import ground, trees
from ..model import Block, Plot, Tree

_DAY = 86400
SMALLEST = 0.45  # how far a tree shrinks to keep clear of its neighbors


def growth(born: float, now: float) -> float:
    age = now - born
    return 0.75 if age < _DAY else 0.88 if age < 3 * _DAY else 1.0


def crowding(plot: Plot, block: Block, sizes: dict[str, float]) -> float:
    """How much to scale every tree in *block* so their crowns cover about a third of its plot:
    larger in a roomy block, smaller in a crowded one.
    """
    crowns = sum(
        (2 * shape.rx) * (2.5 * shape.ry)
        for shape in (trees.shape(tree, "x", sizes[tree.key]) for tree in block.trees)
    )
    return min(1.6, max(0.68, math.sqrt(ground.area(plot) * 0.33 / max(1, crowns))))


Box = tuple[float, float, float, float]  # left, top, right, bottom
# A tag is as wide in cells at any zoom, but the grove view draws a grove unit about this many
# cells wide, so a tag spans fewer units than it has cells.
CELLS_PER_UNIT = 1.4
# At its smallest the grove view draws a grove unit this many rows tall, but a tree and its tag
# are drawn as many rows tall at any zoom, so they need more units of height than rows.
ROWS_PER_UNIT = 0.8


def _boxes(tree: Tree, size: float, x: float, y: float) -> tuple[Box, Box]:
    """A tree's crown and its tag, standing at (*x*, *y*) with *size*."""
    shape = trees.shape(tree, "x", size)
    crown = (x - shape.rx - 1, y - shape.ry * 1.45 - 1, x + shape.rx + 1, y + shape.ry + 1)
    half = shape.width / 2 / CELLS_PER_UNIT
    tag = (x - half, y + shape.ry + 1, x + half, y + shape.ry + 2)
    return crown, tag


def _overlap(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _crowded(boxes: abc.Mapping[str, tuple[Box, Box]]) -> set[str]:
    """Trees whose crown meets another's crown or tag. Tags meeting tags are slid apart when
    drawn, so they don't count.
    """
    return {
        key
        for key, (crown, tag) in boxes.items()
        for other, (their_crown, their_tag) in boxes.items()
        if key != other
        and (
            _overlap(crown, their_crown) or _overlap(crown, their_tag) or _overlap(tag, their_crown)
        )
    }


def spaced(
    block: Block, sizes: dict[str, float], spots: abc.Mapping[str, tuple[float, float]]
) -> tuple[dict[str, float], set[str]]:
    """*sizes*, shrunk where two trees standing at *spots* would grow into each other's crowns,
    and the trees still crowded at their smallest.
    """
    fitted = dict(sizes)
    for _ in range(12):
        crowded = _crowded({t.key: _boxes(t, fitted[t.key], *spots[t.key]) for t in block.trees})
        if not crowded or all(fitted[key] <= SMALLEST for key in crowded):
            return fitted, crowded

        fitted = {
            key: max(SMALLEST, size * 0.9) if key in crowded else size
            for key, size in fitted.items()
        }
    return fitted, crowded
