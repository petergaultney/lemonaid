"""Dragging a bare tree: within its block to move it, or off its block's ground to clear it."""

import dataclasses
from collections import abc
from typing import Any

from ..draw import ground
from ..layout import arrange, edit, lead_spot, room
from .frame import Grove
from .garden import Drag


def _stump(arrangement: arrange.Arrangement, drag: Drag) -> arrange.Stump | None:
    return next(
        (s for s in arrangement.stumps.get(drag.block.name, ()) if s.key == drag.tree), None
    )


def _aim(grove: Grove, drag: Drag) -> tuple[int, int] | None:
    """Where the drag would stand the bare tree in its plot, or None to clear it."""
    stump = _stump(grove.arrangement, drag)
    assert stump is not None  # a drag is let go when the grove reloads
    cx, cy = stump.cx + drag.moved[0], stump.cy + drag.moved[1]
    plot = grove.arrangement.plots[drag.block.name]
    return (cx, cy) if ground.inside(plot, plot.x + cx, plot.y + cy) else None


def _placed(grove: Grove, drag: Drag, aim: tuple[int, int] | None) -> Grove:
    stumps = grove.arrangement.stumps[drag.block.name]
    kept = tuple(
        s if s.key != drag.tree else s._replace(cx=aim[0], cy=aim[1])
        for s in stumps
        if aim is not None or s.key != drag.tree
    )
    arrangement = dataclasses.replace(
        grove.arrangement, stumps={**grove.arrangement.stumps, drag.block.name: kept}
    )
    return dataclasses.replace(grove, arrangement=arrangement)


def dragged(grove: Grove, drag: Drag) -> Grove:
    """*grove* with the bare tree where the drag has it, or gone while it would be cleared."""
    return _placed(grove, drag, _aim(grove, drag))


def _refused(grove: Grove, drag: Drag, aim: tuple[int, int] | None) -> str:
    if aim is None:
        return ""

    name, arrangement = drag.block.name, grove.arrangement
    for tree in drag.block.trees:
        s = arrangement.trees[(name, tree.key)]
        x, y, w, h = room.footprint(tree, s.label, s.letter, s.size, s.cx, s.cy)
        if x <= aim[0] < x + w and y <= aim[1] < y + h:
            return "a tree stands there"
    return ""


def refused(grove: Grove, drag: Drag) -> str:
    return _refused(grove, drag, _aim(grove, drag))


def describe(grove: Grove, drag: Drag) -> str:
    if _aim(grove, drag) is None:
        return f"clearing bare tree {drag.name} · release to clear it · esc puts it back"
    problem = refused(grove, drag)
    if problem:
        return f"moving bare tree {drag.name}: {problem}"
    return (
        f"moving bare tree {drag.name} · release to drop · off its block clears it"
        " · esc puts it back"
    )


def drop(
    grove: Grove, drag: Drag, now: float | None = None
) -> abc.Callable[[dict[str, Any]], dict[str, Any]]:
    """The change to the saved layout that drops *drag*, for `state.update`, checked again against
    the saved layout: it raises EditError if the bare tree's tree came back, or if a move would
    put it off its block's ground or onto a tree, a tree that arrived during the drag among them.
    """
    aim = _aim(grove, drag)
    name = drag.block.name

    def apply(saved: dict[str, Any]) -> dict[str, Any]:
        if aim is None:
            return edit.clear_stump(saved, name, drag.tree)

        changed = edit.place_stump(saved, name, drag.tree, *aim)
        known = {t.key for t in drag.block.trees} | {lead_spot.KEY}
        spots = saved["trees"].get(name, {})
        if any(not s.get("gone_since") and key not in known for key, s in spots.items()):
            raise edit.EditError("the grove changed while you dragged; try again")
        fresh = Grove(grove.blocks, *arrange.arrange(grove.blocks, saved, now))
        plot = fresh.arrangement.plots[name]
        if not ground.inside(plot, plot.x + aim[0], plot.y + aim[1]):
            raise edit.EditError("its block changed while you dragged; try again")
        problem = _refused(fresh, drag, aim)
        if problem:
            raise edit.EditError(problem)
        return changed

    return apply
