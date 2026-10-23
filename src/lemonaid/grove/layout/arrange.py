"""Give every block a plot and every tree a spot and a letter, keeping what was given before.

A group with no live lemons leaves its plot as open ground, and the next new group takes the
open plot nearest the middle. Trees stand in their plots as `stand` places them.
"""

import copy
import dataclasses
import math
import time
from typing import Any

from ..draw import trees
from ..model import WORLD_HEIGHT, WORLD_WIDTH, Block, Plot, Tree
from . import landmarks, placement, room, stand

_STUMP_NAMED_FOR = 2 * 3600  # a stump shows its tree's name, and a few dead leaves, this long


@dataclasses.dataclass(frozen=True)
class Arrangement:
    plots: dict[str, Plot]  # by group name, "" for lemons in no group
    open: tuple[Plot, ...]
    trees: dict[tuple[str, str], stand.Standing]  # by (group name, tree key)
    # Free spots: (cx, cy, when freed, the name of the tree that stood there while it's recent).
    stumps: dict[str, tuple[tuple[int, int, float, str], ...]]
    roads: tuple[tuple[tuple[int, int], ...], ...] = ()
    stream: tuple[tuple[int, int], ...] = ()
    bays: dict[str, int] = dataclasses.field(default_factory=dict)  # highest saved bay, gone or not


def _plot(data: dict[str, Any]) -> Plot:
    return Plot(
        data["x"], data["y"], data["w"], data["h"], data["roundness"], data["seed"], data["texture"]
    )


def _plot_data(plot: Plot) -> dict[str, Any]:
    return {**dataclasses.asdict(plot), "open_since": None}


def _place_plots(blocks: tuple[Block, ...], saved: dict[str, Any], now: float) -> None:
    plots = saved["plots"]
    live = {block.name for block in blocks}
    for name, data in plots.items():
        if name in live:
            data["open_since"] = None
        elif data.get("open_since") is None:
            data["open_since"] = now
    house = plots.get(landmarks.PACKHOUSE)
    if house and house.get("texture") != "house":
        del plots[landmarks.PACKHOUSE]  # from before there was a packhouse: rebuild it
    for block in blocks:
        if block.name in plots:
            continue

        taken = [(d["x"], d["y"], d["w"], d["h"]) for d in plots.values()]
        if block.name == landmarks.PACKHOUSE:
            plots[block.name] = _plot_data(landmarks.packhouse(len(block.trees), taken))
            continue

        open_plots = sorted(
            (
                name
                for name, data in plots.items()
                if data.get("open_since") is not None and name != landmarks.PACKHOUSE
            ),
            key=lambda name: math.hypot(
                plots[name]["x"] + plots[name]["w"] / 2 - WORLD_WIDTH / 2,
                (plots[name]["y"] + plots[name]["h"] / 2 - WORLD_HEIGHT / 2) * 2,
            ),
        )
        if open_plots:
            plots[block.name] = {**plots.pop(open_plots[0]), "open_since": None}
            plots[block.name].pop("crowd", None)  # its trees were another block's
            saved["trees"].pop(open_plots[0], None)
            continue

        need = sum(
            trees.shape(tree, "x", 1.0).width * trees.shape(tree, "x", 1.0).height
            for tree in block.trees
        )
        plots[block.name] = _plot_data(
            placement.new_plot(block.name, placement.plot_size(need), taken)
        )


def _toward_packhouse(name: str, plot: Plot, saved: dict[str, Any]) -> tuple[float, float] | None:
    """The packhouse's middle relative to block *name*'s corner, or None for the packhouse."""
    house = saved["plots"].get(landmarks.PACKHOUSE)
    if name == landmarks.PACKHOUSE or not house:
        return None

    return house["x"] + house["w"] / 2 - plot.x, house["y"] + house["h"] / 2 - plot.y


def _spilled(block: Block, plot: Plot, standing: dict[str, stand.Standing]) -> list[Tree]:
    return [
        tree
        for tree in block.trees
        if not tree.lead
        and not (0 <= standing[tree.key].cx <= plot.w and 0 <= standing[tree.key].cy <= plot.h)
    ]


def _stand(block: Block, kept: dict[str, Any], now: float) -> dict[str, stand.Standing]:
    """Where *block*'s trees stand. A tree that spilled out of its plot, for want of room, takes
    more ground with it where the ground beside the plot is free, and stands afresh in it.
    """
    for _ in range(
        2 * len(block.trees) + 2
    ):  # a growth a spilled tree, and a second if it falls short
        plot = _plot(kept["plots"][block.name])
        standing = stand.stand_trees(
            block,
            plot,
            kept,
            now,
            _toward_packhouse(block.name, plot, kept),
            bays=plot.texture == "house",
        )
        spilled = [] if plot.texture == "house" else _spilled(block, plot, standing)
        if not spilled:
            return standing

        s = standing[spilled[0].key]
        need = room.footprint(spilled[0], s.label, s.letter, s.size, s.cx, s.cy)[2:]
        shift = room.grow(block.name, kept["plots"], need)
        if shift is None:
            return standing

        spots = kept["trees"][block.name]
        for spot in spots.values():
            spot["x"], spot["y"] = spot["x"] + shift[0], spot["y"] + shift[1]
        spots[spilled[0].key] = {"letter": spots[spilled[0].key]["letter"]}
    return standing


def arrange(
    blocks: tuple[Block, ...], saved: dict[str, Any], now: float | None = None
) -> tuple[Arrangement, dict[str, Any]]:
    """The layout for *blocks*, and the saved layout to keep for next time."""
    now = time.time() if now is None else now
    kept = copy.deepcopy(saved)
    kept.setdefault("roads", landmarks.default_roads())
    kept.setdefault("stream", landmarks.default_stream())
    _place_plots(blocks, kept, now)
    standing = {
        (block.name, key): spot
        for block in blocks
        for key, spot in _stand(block, kept, now).items()
    }
    plots = {block.name: _plot(kept["plots"][block.name]) for block in blocks}
    stumps = {
        block.name: tuple(
            (
                s["x"],
                s["y"],
                s["gone_since"],
                s.get("label", key) if now - s["gone_since"] < _STUMP_NAMED_FOR else "",
            )
            for key, s in kept["trees"].get(block.name, {}).items()
            if s.get("gone_since")
        )
        for block in blocks
    }
    open_plots = tuple(_plot(d) for d in kept["plots"].values() if d.get("open_since") is not None)
    roads = tuple(tuple((x, y) for x, y in road) for road in kept["roads"])
    stream = tuple((x, y) for x, y in kept["stream"])
    bays = {
        block.name: max(
            (s["bay"] for s in kept["trees"].get(block.name, {}).values() if "bay" in s), default=0
        )
        for block in blocks
    }
    return Arrangement(plots, open_plots, standing, stumps, roads, stream, bays), kept
