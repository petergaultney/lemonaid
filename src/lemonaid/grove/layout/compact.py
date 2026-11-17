"""A block zoomed in, as the few numbers a lemon gardening it needs, instead of a drawing."""

from typing import NamedTuple

from ..draw import block_scene, canvas, scene_parts, tag_fit
from ..model import Block
from . import stands
from .arrange import Arrangement

Rect = tuple[int, int, int, int]


class Placed(NamedTuple):
    key: str
    letter: str
    spot: tuple[int, int]  # in its plot, as `plant` takes it
    center: tuple[int, int]  # its crown's center on the zoomed screen
    list: Rect  # its lemon list's left, top, width and height on the zoomed screen
    off: str  # why the tree doesn't stand on its list, or empty when it does


def placed(block: Block, arrangement: Arrangement, size: tuple[int, int]) -> list[Placed]:
    """Where each of *block*'s trees (none for the packhouse) and its list stand when the block is zoomed to fill a *size*
    screen. Drawn afresh, so a list the open grove kept where it was before may stand elsewhere.
    """
    if arrangement.plots[block.name].texture == "house":
        return []  # the packhouse's bays aren't trees on the ground

    screen = canvas.blank(*size)
    fitted: dict[str, tag_fit.Fitted] = {}
    lists = block_scene.zoomed(screen, block, arrangement, 0.0, fitted_out=fitted)
    plot = arrangement.plots[block.name]
    view = scene_parts.block_view(screen, arrangement, block)
    found = []
    for tree in block.trees:
        s = arrangement.trees[(block.name, tree.key)]
        if tree.key not in lists:
            continue

        found.append(
            Placed(
                tree.key,
                s.letter,
                (s.cx, s.cy),
                tuple(round(c) for c in view.screen(plot.x + s.cx, plot.y + s.cy)),
                lists[tree.key],
                stands.off(fitted[tree.key], lists[tree.key]),
            )
        )
    return found


def lines(block: Block, arrangement: Arrangement, size: tuple[int, int]) -> list[str]:
    """One line per tree: its place in the plot, its crown's center and its list on the zoomed screen."""
    return [
        f"{block.digit}{p.letter} {p.key}: spot {p.spot[0]},{p.spot[1]}; crown at "
        f"{p.center[0]},{p.center[1]}; list {p.list[2]}x{p.list[3]} at {p.list[0]},{p.list[1]}"
        + (f"; off its list: {p.off}" if p.off else "; stands on its list")
        for p in placed(block, arrangement, size)
    ]
