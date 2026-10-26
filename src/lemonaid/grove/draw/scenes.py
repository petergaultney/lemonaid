"""The whole grove, zoomed out to fit the screen."""

from collections import abc

from ..layout.arrange import Arrangement
from ..model import Block
from . import house, plots, scene_parts
from .canvas import Canvas


def overview(
    canvas: Canvas,
    blocks: abc.Sequence[Block],
    arrangement: Arrangement,
    phase: float,
    highlight: scene_parts.Highlight | None = None,
    pan: tuple[float, float] = (0.0, 0.0),
) -> None:
    """The whole grove, scaled to fit the screen below its title row and above its prompt row,
    or panned to *pan* when it can't fit.
    """
    if not scene_parts.fits(canvas):
        return

    view = scene_parts.grove_view((canvas.width, canvas.height), arrangement, pan)
    scale = min(view.sx, view.sy)
    plots.speckle(canvas)
    plots.stream(canvas, view, arrangement.stream)
    for road in arrangement.roads:
        plots.road(canvas, view, road)
    for plot in arrangement.open:
        plots.ground(canvas, plot, view, "#000000", live=False)
    taken = []
    planted = []
    signs = []
    for block in blocks:
        plot = arrangement.plots[block.name]
        if plot.texture == "house":
            taken.append(
                house.draw(
                    canvas,
                    block,
                    arrangement,
                    view,
                    phase,
                    lambda tree: (
                        scene_parts.fade(highlight, scene_parts.tree_channels(tree)) * 0.75
                    ),
                )
            )
            continue

        block_dim = scene_parts.fade(highlight, scene_parts.block_channels(block))
        canvas.dim, canvas.target = block_dim, (block.digit,)
        plots.ground(canvas, plot, view, block.color, live=True)
        taken.append(plots.sign(canvas, plot, view, block.digit, block.name, block.color))
        signs.append((plot, block))
        for stump in arrangement.stumps.get(block.name, ()):
            plots.stump(canvas, *view.screen(plot.x + stump.cx, plot.y + stump.cy), stump.label)
        canvas.dim, canvas.target = 0.0, ()
        left, right = (round(view.screen(x, plot.y)[0]) for x in (plot.x, plot.x + plot.w))
        planted += [
            scene_parts.Planted(
                block,
                tree,
                scene_parts.place_tree(block, tree, arrangement, view, scale, False),
                scene_parts.fade(highlight, scene_parts.tree_channels(tree))
                * (0.75 if block_dim == 0 else 1),
                (left, right),
                whole_key=True,
            )
            for tree in block.trees
        ]
    scene_parts.plant(canvas, planted, arrangement, phase, highlight, taken)
    for plot, block in signs:  # again, over any pennant that reached a sign
        canvas.dim = scene_parts.fade(highlight, scene_parts.block_channels(block))
        plots.sign(canvas, plot, view, block.digit, block.name, block.color)
    canvas.dim = 0.0
