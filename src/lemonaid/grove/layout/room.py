"""Whether a block's trees stand clear of each other."""

import dataclasses
from collections import abc

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
