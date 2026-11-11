"""One block zoomed in to fill the screen, each tree with its lemons listed beside it."""

import dataclasses
import math

from ..layout.arrange import Arrangement
from ..model import Block
from . import house, lemon_list, list_spot, plots, scene_parts, trees
from .canvas import Canvas

Spot = tuple[int, int, float]  # a list's top left, and how much it covered when put there
Rect = list_spot.Rect


def zoomed(
    canvas: Canvas,
    block: Block,
    arrangement: Arrangement,
    phase: float,
    highlight: scene_parts.Highlight | None = None,
    opened: str = "",
    lists: dict[str, Spot] | None = None,
    tallest: float = trees.GROWN,
    flipped: bool = False,
    key_prefix: str = "",
) -> dict[str, Rect]:
    """*block* filling the screen, each tree with its lemons listed beside it; returns where each
    tree's list went. *opened* is the
    letter of a tree whose lemons are being picked by number. *lists*, where each tree's list was
    drawn last time, keeps a list there while it covers no more than it did then, and is told
    where each one goes. Its trees' crowns grow no taller than *tallest* rows from their centers.
    *flipped* shows each list's other page. *key_prefix* goes before each tree's key, as select
    mode's `$` that chooses a whole tree.
    """
    lists = {} if lists is None else lists
    if not scene_parts.fits(canvas):
        return {}

    plot = arrangement.plots[block.name]
    if plot.texture == "house":
        return house.zoomed(
            canvas,
            block,
            arrangement,
            phase,
            highlight.channels if highlight else None,
            opened,
            highlight.edited if highlight else "",
            flipped,
            key_prefix,
        )

    view = scene_parts.block_view(canvas, arrangement, block)
    plots.speckle(canvas)
    canvas.target = (block.digit,)
    plots.ground(canvas, plot, view, block.color, live=True)
    sign = plots.sign(canvas, plot, view, block.digit, block.name, block.color)
    for stump in arrangement.stumps.get(block.name, ()):
        canvas.target = (block.digit, "", stump.key)  # what a drag takes hold of; no letter
        plots.stump(canvas, *view.screen(plot.x + stump.cx, plot.y + stump.cy), stump.label)
    canvas.target = ()
    # As the grove view scales its trees, so a block's trees fill it as they do there.
    scale = max(1.0, min(view.sx, view.sy))
    planted = [
        scene_parts.Planted(
            block,
            tree,
            scene_parts.place_tree(
                block, tree, arrangement, view, scale, True, tallest, key_prefix
            ),
            scene_parts.fade(highlight, scene_parts.tree_channels(tree)) * 0.75,
            (1, canvas.width - 1),
            key_prefix=key_prefix,
        )
        for tree in block.trees
    ]
    fitted = scene_parts.plant(
        canvas, planted, arrangement, phase, highlight, [sign], tags_drawn=False
    )
    crowns = [trees.crown_box(p.placed[2], *p.placed[:2]) for p in planted]
    taken = [list_spot.footprint(c, tag) for c, tag in zip(crowns, fitted, strict=True)]
    trees_at = list(enumerate(taken))  # each tree's footprint, by its place in *planted*
    spots: dict[str, tuple[int, int]] = {}
    letters = [arrangement.trees[(block.name, p.tree.key)].letter for p in planted]
    caps: list[Rect] = []  # the letters of the titles placed so far, kept in sight
    w = lemon_list.width(canvas.width)
    # Lists where they were last drawn first, while they cover no more than they did there, so
    # a list in a crowded block stays put as its neighbors change; then the rest.
    for i in sorted(range(len(planted)), key=lambda i: planted[i].tree.key not in lists):
        p = planted[i]
        rows = len(p.tree.lemons) + 2  # its lemons, and its box's edges
        was = lists.get(p.tree.key)
        now = list_spot.crowding(canvas, (was[0], was[1], w, rows), taken) if was else math.inf
        hides = was and list_spot.overlap((was[0], was[1], w, rows), caps)
        if was and now < math.inf and now <= was[2] and not hides:
            x, y, covered = was
        else:
            others = [f for j, f in trees_at if j != i]
            x, y = list_spot.spot(canvas, crowns[i], fitted[i], others, w, rows, taken, caps)
            covered = list_spot.crowding(canvas, (x, y, w, rows), taken)
        spots[p.tree.key] = (x, y)
        caps.append((x + 2, y, len(key_prefix + letters[i]), 1))
        lists[p.tree.key] = (x, y, covered)
        taken.append((x, y, w, rows))
    titles = []
    for p in planted:
        letter = arrangement.trees[(block.name, p.tree.key)].letter
        labeled = dataclasses.replace(
            p.tree, label=arrangement.trees[(block.name, p.tree.key)].label
        )
        title = trees.short_tag(labeled, key_prefix + letter, w - 4).rstrip() + " "
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
            edited=highlight.edited if highlight else "",
            flipped=flipped,
            width=w,
            tagged=len(title),
        )
        titles.append((p, labeled, title, x, y, letter))
    # Every list's title, the tree's tag, over all the lists, so where a crowded screen makes lists
    # overlap, each tree's tag still shows.
    for p, labeled, title, x, y, letter in titles:
        canvas.dim = p.dim
        canvas.target = (block.digit, letter)
        trees.draw_tag(
            canvas, labeled, (title,), x + 1, y, (x + 1, y), phase, key=len(key_prefix + letter)
        )
    canvas.target = ()
    canvas.dim = 0.0
    return {p.tree.key: (*spots[p.tree.key], w, len(p.tree.lemons) + 2) for p in planted}
