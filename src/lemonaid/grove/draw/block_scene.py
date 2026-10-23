"""One block zoomed in to fill the screen, each tree with its lemons listed beside it."""

from collections import abc

from ..layout.arrange import Arrangement
from ..model import Block
from . import house, lemon_list, plots, scene_parts, tag_fit, trees
from .canvas import Canvas


def zoomed(
    canvas: Canvas,
    block: Block,
    arrangement: Arrangement,
    phase: float,
    highlight: scene_parts.Highlight | None = None,
    opened: str = "",
    lists: dict[str, tuple[int, int]] | None = None,
) -> None:
    """*block* filling the screen, each tree with its lemons listed beside it. *opened* is the
    letter of a tree whose lemons are being picked by number. *lists*, where each tree's list was
    drawn last time, keeps a list there while it covers nothing, and is told where each one goes.
    """
    lists = {} if lists is None else lists
    if not scene_parts.fits(canvas):
        return

    plot = arrangement.plots[block.name]
    if plot.texture == "house":
        house.zoomed(
            canvas, block, arrangement, phase, highlight.channels if highlight else None, opened
        )
        return

    view = scene_parts.block_view(canvas, arrangement, block)
    plots.speckle(canvas)
    canvas.target = (block.digit,)
    plots.ground(canvas, plot, view, block.color, live=True)
    sign = plots.sign(canvas, plot, view, block.digit, block.name, block.color)
    for cx, cy, _, label in arrangement.stumps.get(block.name, ()):
        plots.stump(canvas, *view.screen(plot.x + cx, plot.y + cy), block.color, label)
    canvas.target = ()
    scale = min(1.6, max(1.0, min(view.sx, view.sy) * 0.8))
    planted = [
        scene_parts.Planted(
            block,
            tree,
            scene_parts.place_tree(block, tree, arrangement, view, scale, True),
            scene_parts.fade(highlight, scene_parts.tree_channels(tree)) * 0.75,
            (1, canvas.width - 1),
        )
        for tree in block.trees
    ]
    fitted = scene_parts.plant(canvas, planted, arrangement, phase, highlight, [sign])
    taken = [_footprint(p, tag) for p, tag in zip(planted, fitted, strict=True)]
    footprints = dict(zip((p.tree.key for p in planted), list(taken), strict=True))
    spots: dict[str, tuple[int, int]] = {}
    # Lists where they were last drawn first, while they still cover nothing, then the rest.
    for p in sorted(planted, key=lambda p: p.tree.key not in lists):
        rows = len(p.tree.lemons) + 2  # its lemons, and its box's edges
        was = lists.get(p.tree.key)
        clear = was and _fits_at(canvas, (*was, lemon_list.WIDTH, rows), taken)
        x, y = (
            was if clear else _list_spot(canvas, p.placed[0], footprints[p.tree.key], rows, taken)
        )
        spots[p.tree.key] = lists[p.tree.key] = (x, y)
        taken.append((x, y, lemon_list.WIDTH, rows))
    for p in planted:
        letter = arrangement.trees[(block.name, p.tree.key)].letter
        x, y = spots[p.tree.key]
        canvas.dim = p.dim
        canvas.target = (block.digit, letter)
        lemon_list.draw(
            canvas,
            x,
            y,
            p.tree,
            letter,
            block.color,
            phase,
            highlight.channels if highlight else None,
            letter == opened,
        )
        canvas.target = ()
        canvas.dim = 0.0


Rect = tuple[int, int, int, int]
_GAP = 2  # columns kept clear beside a list; one row above and below


def _footprint(planted: scene_parts.Planted, tag: tag_fit.Fitted) -> Rect:
    """The tree and its tag together."""
    ax, ay, shape = planted.placed
    x, y, w, _ = trees.crown_box(shape, ax, ay)
    left, right = min(x, tag.x), max(x + w, tag.x + len(tag.lines[0]))
    return left, y, right - left, tag.y + len(tag.lines) - y


def _overlap(a: Rect, others: abc.Iterable[Rect]) -> int:
    x, y, w, h = a
    return sum(
        max(0, min(x + w, ox + ow) - max(x, ox)) * max(0, min(y + h, oy + oh) - max(y, oy))
        for ox, oy, ow, oh in others
    )


def _attached(ax: float, footprint: Rect, w: int, height: int) -> list[tuple[int, int]]:
    """Spots for a list touching its tree, best first: below the tag, above the crown, then
    beside it. Above or below, the list may slide sideways while it still spans the trunk.
    """
    fx, fy, fw, fh = footprint
    trunk = round(ax)
    centered = trunk - w // 2
    slides = sorted(range(trunk - w + 4, trunk - 2, 2), key=lambda x: abs(x - centered))
    return [
        *((x, fy + fh + 1) for x in slides),
        *((x, fy - height - 1) for x in slides),
        *((fx + fw + _GAP, y) for y in range(fy, fy + max(1, fh - height + 1))),
        *((fx - w - _GAP, y) for y in range(fy, fy + max(1, fh - height + 1))),
    ]


def _fits_at(canvas: Canvas, rect: Rect, taken: list[Rect]) -> bool:
    x, y, w, h = rect
    clear = [(tx - _GAP, ty - 1, tw + 2 * _GAP, th + 2) for tx, ty, tw, th in taken]
    on_screen = x >= 1 and x + w <= canvas.width - 1 and y >= 1 and y + h <= canvas.height - 1
    return on_screen and _overlap(rect, clear) == 0


def _list_spot(
    canvas: Canvas, ax: float, footprint: Rect, height: int, taken: list[Rect]
) -> tuple[int, int]:
    """The best spot touching the tree that overlaps nothing, else the one overlapping least:
    a list never leaves its tree, so on a crowded screen it may cover a neighbor a little.
    """
    w = lemon_list.WIDTH
    clear = [(x - _GAP, y - 1, rw + 2 * _GAP, rh + 2) for x, y, rw, rh in taken]
    spots = [
        (min(max(1, x), canvas.width - w - 1), min(max(1, y), canvas.height - height - 2))
        for x, y in _attached(ax, footprint, w, height)
    ]
    return min(spots, key=lambda spot: _overlap((*spot, w, height), clear))
