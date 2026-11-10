"""Where a drag in the grove would put its block or tree, whether it can go there, and saving it."""

import dataclasses
from collections import abc
from typing import Any

from ..draw import ground, plots, refusal
from ..layout import arrange, edit, lead_spot, placement, room, sizes, terrain
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
    if drag.open >= 0:
        return _plot(grove.arrangement.open[drag.open], drag)
    return _plot(grove.arrangement.plots[drag.block.name], drag)


def _placed(grove: Grove, drag: Drag, aim: Aim) -> Grove:
    name, arrangement = drag.block.name, grove.arrangement
    if drag.open >= 0 and isinstance(aim, Plot):
        grounds = list(arrangement.open)
        grounds[drag.open] = aim
        return dataclasses.replace(
            grove, arrangement=dataclasses.replace(arrangement, open=tuple(grounds))
        )

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


def _on_terrain(arrangement: arrange.Arrangement, plot: Plot, drag: Drag) -> str:
    """Judged as drawn in the view the drag is made in, so a block can come right up to them on
    screen; and as saving judges it, where they run on past the world's edges.
    """
    roads, stream = arrangement.roads, arrangement.stream
    crossed = plot.texture != "house" and (
        plots.over_terrain(plot, plots.View(*drag.origin, *drag.scale), roads, stream)
        or terrain.crosses(terrain.under(roads, stream), plot)
    )
    return "a road or the stream runs there" if crossed else ""


def _refused_open(grove: Grove, drag: Drag, aim: Aim) -> str:
    plot = _placed(grove, drag, aim).arrangement.open[drag.open]
    if plot.w < 12 or plot.h < 5:
        return "open ground needs at least 12 columns and 5 rows"
    if plot.x < 0 or plot.y < 1:
        return "that's past the grove's edge"
    if any(
        placement.overlaps((plot.x, plot.y, plot.w, plot.h), (p.x, p.y, p.w, p.h), 0)
        for p in grove.arrangement.plots.values()
    ):
        return "a block's ground is there"
    return _on_terrain(grove.arrangement, plot, drag)


def _refused(grove: Grove, drag: Drag, aim: Aim) -> str:
    if drag.open >= 0:
        return _refused_open(grove, drag, aim)

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
    others = [p for other, p in after.plots.items() if other != name]  # open ground is built over
    if any(_on_ground_of(plot, other) for other in others):
        return "another block's ground is there"
    if crossed := _on_terrain(after, plot, drag):
        return crossed
    try:
        if drag.sides and _crowded(grove, drag.block, plot):
            return "its trees need more room than that"
    except edit.EditError as error:
        return str(error)
    return ""


def refused(grove: Grove, drag: Drag) -> str:
    """Why the drag can't be dropped where it is, or "" when it can."""
    if drag.stump:
        return stump_drag.refused(grove, drag)
    return _refused(grove, drag, _aim(grove, drag))


def describe(grove: Grove, drag: Drag, problem: str) -> str:
    """What *drag* is doing, for the prompt; *problem* is what `refused` says of it."""
    if drag.stump:
        return stump_drag.describe(grove, drag, problem)
    return garden.describe(drag, problem)


def shown_refused(grove: Grove, drag: Drag) -> refusal.Refusal:
    """What to draw red while *drag* is refused: its tree or bare tree, or the ground it'd take."""
    if drag.stump:
        return refusal.Refusal(target=(drag.block.digit, "", drag.tree))
    if drag.tree:
        letter = grove.arrangement.trees[(drag.block.name, drag.tree)].letter
        return refusal.Refusal(target=(drag.block.digit, letter))
    aim = _aim(grove, drag)
    return refusal.Refusal(plot=aim if isinstance(aim, Plot) else None)


def _still_open(drag: Drag, saved: dict[str, Any]) -> str:
    """The saved key of the open ground *drag* began on, or raise EditError if it has since gone,
    been taken over or been moved.
    """
    was = drag.open_was
    for name, plot in saved["plots"].items():
        if (
            plot.get("open_since") is not None
            and was is not None
            and (plot["x"], plot["y"], plot["w"], plot["h"], plot["seed"])
            == (was.x, was.y, was.w, was.h, was.seed)
        ):
            return name
    raise edit.EditError("that open ground changed while you dragged; try again")


def _index_of(arrangement: arrange.Arrangement, drag: Drag) -> int:
    for index, plot in enumerate(arrangement.open):
        if plot == drag.open_was:
            return index
    raise edit.EditError("that open ground changed while you dragged; try again")


def _edit_open(drag: Drag, aim: Plot) -> abc.Callable[[dict[str, Any]], dict[str, Any]]:
    def change(saved: dict[str, Any]) -> dict[str, Any]:
        name = _still_open(drag, saved)
        if not drag.sides:
            return edit.move(saved, name, aim.x, aim.y)
        return edit.reframe(saved, name, aim.x, aim.y, aim.w, aim.h)

    return change


def _edit(drag: Drag, aim: Aim) -> abc.Callable[[dict[str, Any]], dict[str, Any]]:
    if drag.open >= 0 and isinstance(aim, Plot):
        return _edit_open(drag, aim)

    name = drag.block.name
    if isinstance(aim, tuple):
        lead = next(t for t in drag.block.trees if t.key == drag.tree).lead
        return lambda saved: edit.place_tree(saved, name, drag.tree, lead, *aim)
    if not drag.sides:
        return lambda saved: edit.move(saved, name, aim.x, aim.y)
    return lambda saved: edit.reframe(saved, name, aim.x, aim.y, aim.w, aim.h)


def _stands(arrangement: arrange.Arrangement, drag: Drag) -> Aim:
    if drag.open >= 0:
        return arrangement.open[drag.open]

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
        nonlocal drag
        if drag.open >= 0:
            _still_open(drag, saved)
        known = {t.key for t in drag.block.trees} | {lead_spot.KEY}
        spots = {} if drag.open >= 0 else saved["trees"].get(drag.block.name, {})
        if any(not s.get("gone_since") and key not in known for key, s in spots.items()):
            raise edit.EditError("the grove changed while you dragged; try again")

        fresh = Grove(grove.blocks, *arrange.arrange(grove.blocks, saved, now))
        if drag.open >= 0:
            drag = dataclasses.replace(drag, open=_index_of(fresh.arrangement, drag))
        problem = _refused(fresh, drag, aim)
        if problem:
            raise edit.EditError(problem)

        changed = _edit(drag, aim)(saved)
        if _stands(arrange.arrange(grove.blocks, changed, now)[0], drag) != aim:
            raise edit.EditError("the grove would move it from there; try farther from the rest")
        return changed

    return apply
