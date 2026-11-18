"""Where a tree may stand in its block: its trunk and the tag it stands on on the block's ground,
and its crown within the block's sides.

Judged at the tree's smallest, which the layout shrinks a tree to near an edge, and a row to a
grove unit. A tag isn't judged by its width: it slides and shortens to stay within its block.
"""

from ..draw import ground, trees
from ..model import Plot, Tree
from . import sizes

_TAG_BELOW = 2  # rows from a crown's lowest row to its tag's


def _reach(tree: Tree) -> tuple[int, int, float]:
    """How far the crown reaches left and right of the trunk, as placement measures a footprint,
    and how far below the crown's center the tag is.
    """
    shape = trees.shape(tree, "x", sizes.SMALLEST)
    width = round(2 * shape.rx) + 2
    return width // 2, width - width // 2, shape.ry + _TAG_BELOW


def spills(tree: Tree, plot: Plot, x: float, y: float) -> bool:
    """Whether *tree* standing at (*x*, *y*) in *plot* reaches past the plot's box, but for a crown
    rising above it: such a tree stands afresh on its plot.
    """
    left, right, tag = _reach(tree)
    return y < 0 or x - left < 0 or x + right > plot.w or y + tag > plot.h


def refusal(tree: Tree, plot: Plot, x: float, y: float) -> str:
    """Why *tree* can't stand at (*x*, *y*) in *plot*, or "" when it can. Stricter than `spills`:
    the trunk and the tag must also be on the block's rounded ground.
    """
    left, right, tag = _reach(tree)
    if not ground.inside(plot, plot.x + x, plot.y + y):
        return "its trunk would be off the block"
    if x - left < 0:
        return "its crown would reach past the block's left edge"
    if x + right > plot.w:
        return "its crown would reach past the block's right edge"
    if y + tag > plot.h or not ground.inside(plot, plot.x + x, plot.y + y + tag):
        return "its tag would hang below the block's bottom edge"
    return ""
