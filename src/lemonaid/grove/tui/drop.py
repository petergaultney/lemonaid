"""Where a drag in the grove would put its block or tree, whether it can go there, and saving it."""

import dataclasses
from collections import abc
from typing import Any

from ..draw import ground
from ..layout import arrange, edit, lead_spot, room, sizes
from ..model import Block, Plot
from . import garden, stump_drag
from .frame import Grove
from .garden import Drag


def _plot(plot: Plot, drag: Drag) -> Plot:
    dx, dy = drag.moved
    if not drag.sides:
        return dataclasses.replace(plot, x=plot.x + dx, y=plot.y + dy)

    left = plot.x + dx * ("left" in drag.sides)
    top = plot.y + dy * ("top" in drag.sides)
    right = plot.x + plot.w + dx * ("right" in drag.sides)
    bottom = plot.y + plot.h + dy * ("bottom" in drag.sides)
    # At least a cell each way, to draw; `_refused` turns down anything that small.
    return dataclasses.replace(plot, x=left, y=top, w=max(1, right - left), h=max(1, bottom - top))


# Where a drag would put its tree, as (cx, cy) in its plot, or its block's plot.
Aim = tuple[int, int] | Plot


def _aim(grove: Grove, drag: Drag) -> Aim:
    if drag.tree:
        was = grove.arrangement.trees[(drag.block.name, drag.tree)]
        return was.cx + drag.moved[0], was.cy + drag.moved[1]
    return _plot(grove.arrangement.plots[drag.block.name], drag)


def _placed(grove: Grove, drag: Drag, aim: Aim) -> Grove:
    name, arrangement = drag.block.name, grove.arrangement
    if isinstance(aim, tuple):
        spot = dataclasses.replace(arrangement.trees[(name, drag.tree)], cx=aim[0], cy=aim[1])
        trees = {**arrangement.trees, (name, drag.tree): spot}
        return dataclasses.replace(grove, arrangement=dataclasses.replace(arrangement, trees=trees))

    old = arrangement.plots[name]
    shift = (old.x - aim.x, old.y - aim.y) if drag.sides else (0, 0)
    trees = {
        key: dataclasses.replace(s, cx=s.cx + shift[0], cy=s.cy + shift[1]) if key[0] == name else s
        for key, s in arrangement.trees.items()
    }
    plots = {**arrangement.plots, name: aim}
    return dataclasses.replace(
        grove, arrangement=dataclasses.replace(arrangement, plots=plots, trees=trees)
    )


def dragged(grove: Grove, drag: Drag) -> Grove:
    if drag.stump:
        return stump_drag.dragged(grove, drag)
    return _placed(grove, drag, _aim(grove, drag))


def _tangled(block: Block, arrangement: arrange.Arrangement) -> bool:
    oldest_first = sorted(block.trees, key=lambda t: (not t.lead, t.born, t.key))
    # At their smallest, as the layout judges it: trees near each other shrink to fit.
    footprints = (
        (t, room.footprint(t, s.label, s.letter, sizes.SMALLEST, s.cx, s.cy))
        for t in oldest_first
        for s in [arrangement.trees[(block.name, t.key)]]
    )
    return bool(room.tangled(footprints))


def _crowded(grove: Grove, block: Block, plot: Plot) -> bool:
    """Whether *block* resized to *plot* is too small for its trees: the layout would put it
    elsewhere, or make it bigger, or its trees would stand on each other.
    """
    resized = edit.reframe(grove.saved, block.name, plot.x, plot.y, plot.w, plot.h)
    laid_out = arrange.arrange(grove.blocks, resized)[0]
    if laid_out.plots[block.name] != plot:
        return True

    return _tangled(block, laid_out) and not _tangled(block, grove.arrangement)


def _on_ground_of(plot: Plot, other: Plot) -> bool:
    """Whether the two plots' ground, not just their boxes, shares a grove unit: rounded blocks
    can tuck a corner into each other's box.
    """
    left, right = max(plot.x, other.x), min(plot.x + plot.w, other.x + other.w)
    top, bottom = max(plot.y, other.y), min(plot.y + plot.h, other.y + other.h)
    return any(
        ground.inside(plot, x + 0.5, y + 0.5) and ground.inside(other, x + 0.5, y + 0.5)
        for y in range(top, bottom)
        for x in range(left, right)
    )


def _refused(grove: Grove, drag: Drag, aim: Aim) -> str:
    name = drag.block.name
    after = _placed(grove, drag, aim).arrangement
    plot = after.plots[name]
    if drag.tree:
        s = after.trees[(name, drag.tree)]
        if not ground.inside(plot, plot.x + s.cx, plot.y + s.cy):
            return "a tree stays on its block's ground"
        return "another tree stands there" if _tangled(drag.block, after) else ""

    if plot.w < 12 or plot.h < 5:
        return "a block needs at least 12 columns and 5 rows"
    if plot.x < 0 or plot.y < 1:
        return "that's past the grove's edge"
    others = [p for other, p in after.plots.items() if other != name] + list(after.open)
    if any(_on_ground_of(plot, other) for other in others):
        return "another block's ground is there"
    if drag.sides and _crowded(grove, drag.block, plot):
        return "its trees need more room than that"
    return ""


def refused(grove: Grove, drag: Drag) -> str:
    """Why the drag can't be dropped where it is, or "" when it can."""
    if drag.stump:
        return stump_drag.refused(grove, drag)
    return _refused(grove, drag, _aim(grove, drag))


def describe(grove: Grove, drag: Drag) -> str:
    if drag.stump:
        return stump_drag.describe(grove, drag)
    return garden.describe(drag, refused(grove, drag))


def _edit(drag: Drag, aim: Aim) -> abc.Callable[[dict[str, Any]], dict[str, Any]]:
    name = drag.block.name
    if isinstance(aim, tuple):
        lead = next(t for t in drag.block.trees if t.key == drag.tree).lead
        return lambda saved: edit.place_tree(saved, name, drag.tree, lead, *aim)
    if not drag.sides:
        return lambda saved: edit.move(saved, name, aim.x, aim.y)
    return lambda saved: edit.reframe(saved, name, aim.x, aim.y, aim.w, aim.h)


def _stands(arrangement: arrange.Arrangement, drag: Drag) -> Aim:
    if drag.tree:
        s = arrangement.trees[(drag.block.name, drag.tree)]
        return s.cx, s.cy
    return arrangement.plots[drag.block.name]


def drop(
    grove: Grove, drag: Drag, now: float | None = None
) -> abc.Callable[[dict[str, Any]], dict[str, Any]]:
    """The change to the saved layout that drops *drag*, for `state.update`. It checks the drop
    again against the saved layout, which another grove may have changed since *grove* was
    drawn, and raises EditError if the drop can't go there, or if laying the grove out again
    would move it.
    """
    if drag.stump:
        return stump_drag.drop(grove, drag, now)
    aim = _aim(grove, drag)

    def apply(saved: dict[str, Any]) -> dict[str, Any]:
        known = {t.key for t in drag.block.trees} | {lead_spot.KEY}
        spots = saved["trees"].get(drag.block.name, {})
        if any(not s.get("gone_since") and key not in known for key, s in spots.items()):
            raise edit.EditError("the grove changed while you dragged; try again")

        fresh = Grove(grove.blocks, *arrange.arrange(grove.blocks, saved, now))
        problem = _refused(fresh, drag, aim)
        if problem:
            raise edit.EditError(problem)

        changed = _edit(drag, aim)(saved)
        if _stands(arrange.arrange(grove.blocks, changed, now)[0], drag) != aim:
            raise edit.EditError("the grove would move it from there; try farther from the rest")
        return changed

    return apply
