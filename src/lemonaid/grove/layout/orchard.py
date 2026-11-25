"""Trees scale: each group one tree on a plot of its own, each of its lemons with a letter.

A saved layout is in one scale at a time. The other scale's plots, tree spots, roads and
packhouse are kept under `other_scale`, so switching back restores them. Plots stand in rows from
the top left, each new one in the first free room, and keep their place; a group's lemons keep
their letters while they're gone, for a while, as a tree's spot is kept.
"""

import dataclasses
import math
from collections import abc
from typing import Any

from ..model import Block, Plot
from . import labels, letters, stand

_SCALE_KEYS = ("plots", "trees", "aside", "packhouse", "roads", "stream")
_FORGET_AFTER = 30 * 86400  # a gone lemon's letter
_FORGET_PLOT_AFTER = 86400  # a gone group's plot, so the orchard closes up
_ROW = 150  # how far a row of plots runs before the next starts below it
_GAP = 4
_WIDTH = 46  # a crown, and a list of lemons beside it


def is_trees(saved: abc.Mapping[str, Any]) -> bool:
    return saved.get("scale") == "trees"


def with_scale(saved: dict[str, Any], trees: bool) -> dict[str, Any]:
    """*saved* in trees scale or blocks scale, the other's layout kept under `other_scale`."""
    if is_trees(saved) == trees:
        return {**saved, "scale": "trees" if trees else "blocks"}

    leaving = {k: saved[k] for k in _SCALE_KEYS if k in saved}
    rest = {k: v for k, v in saved.items() if k not in _SCALE_KEYS and k != "other_scale"}
    coming = {"plots": {}, "trees": {}} | saved.get("other_scale", {})
    return {**rest, **coming, "scale": "trees" if trees else "blocks", "other_scale": leaving}


def fixed(texture: str) -> str:
    """Why a tree on a plot of *texture* can't be moved by hand, or "" when it can."""
    return {
        "house": "the packhouse's bays stay in order",
        "orchard": "a group tree's lemons stay in order",
    }.get(texture, "")


def _plot_data(x: int, y: int, lemons: int) -> dict[str, Any]:
    plot = Plot(x, y, _WIDTH, max(12, lemons + 7), 6.0, 0, "orchard")
    return {**dataclasses.asdict(plot), "open_since": None}


def _overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return (
        a[0] < b[0] + b[2] + _GAP
        and b[0] < a[0] + a[2] + _GAP
        and a[1] < b[1] + b[3] + _GAP
        and b[1] < a[1] + a[3] + _GAP
    )


def _free_corner(plots: abc.Iterable[dict[str, Any]], size: tuple[int, int]) -> tuple[int, int]:
    """The top left of the first free room for a plot of *size*, row by row from the top left,
    so a new group takes the room a group that ended left.
    """
    taken = [(p["x"], p["y"], p["w"], p["h"]) for p in plots]
    rows = sorted({2, *(y + h + _GAP for _, y, _, h in taken)})
    columns = sorted({2, *(x + w + _GAP for x, _, w, _ in taken)})
    return next(
        (x, y)
        for y in rows
        for x in columns
        if x + size[0] <= _ROW or x == 2
        if not any(_overlaps((x, y, *size), other) for other in taken)
    )


def _place_plots(blocks: abc.Sequence[Block], saved: dict[str, Any], now: float) -> None:
    plots = saved["plots"]
    live = {block.name for block in blocks}
    for name, data in list(plots.items()):
        if name in live:
            data["open_since"] = None
        elif data.get("open_since") is None:
            data["open_since"] = now
        elif now - data["open_since"] > _FORGET_PLOT_AFTER:
            del plots[name]
    for block in blocks:
        if block.name not in plots:
            data = _plot_data(0, 0, len(block.trees) + 1)
            x, y = _free_corner(plots.values(), (data["w"], data["h"]))
            plots[block.name] = {**data, "x": x, "y": y}


def _letters(block: Block, saved: dict[str, Any], now: float) -> dict[str, Any]:
    """Each of *block*'s lemons' saved letter, a new one taking its session's from blocks scale."""
    spots: dict[str, Any] = saved["trees"].setdefault(block.name, {})
    blocks_scale = saved.get("other_scale", {}).get("trees", {}).get(block.name, {})
    live = {tree.key for tree in block.trees}
    for key, spot in list(spots.items()):
        if key in live:
            spot["gone_since"] = None
        elif spot.get("gone_since") is None:
            spot["gone_since"] = now
        elif now - spot["gone_since"] > _FORGET_AFTER:
            del spots[key]
    for tree in block.trees:
        if tree.key not in spots:
            spots[tree.key] = {
                "letter": blocks_scale.get(tree.key, {}).get("letter", ""),
                "gone_since": None,
            }
    short = {t.key: labels.without_group(block.name, t.label) for t in block.trees}
    letters.settle(block.trees, spots, short)
    for tree in block.trees:
        spots[tree.key]["label"] = short[tree.key]
    return spots


def _plot(data: dict[str, Any]) -> Plot:
    return Plot(
        data["x"], data["y"], data["w"], data["h"], data["roundness"], data["seed"], data["texture"]
    )


def arrange(
    blocks: abc.Sequence[Block], saved: dict[str, Any], now: float
) -> tuple[dict[str, Plot], dict[tuple[str, str], stand.Standing], tuple[int, int]]:
    """Each block's plot and each lemon's standing, its place in its group's list as its bay, and
    how far the plots reach; *saved* is updated in place.
    """
    saved.setdefault("plots", {})
    saved.setdefault("trees", {})
    _place_plots(blocks, saved, now)
    standing = {}
    for block in blocks:
        plot = saved["plots"][block.name]
        spots = _letters(block, saved, now)
        for i, tree in enumerate(block.trees):
            standing[(block.name, tree.key)] = stand.Standing(
                plot["w"] // 4,
                plot["h"] // 2,
                labels.LEAD_LETTER if tree.lead else spots[tree.key]["letter"],
                spots[tree.key]["label"],
                1.0,
                i,
            )
    plots = {block.name: _plot(saved["plots"][block.name]) for block in blocks}
    reach = (
        max((p.x + p.w for p in plots.values()), default=0) + 2,
        max((p.y + p.h for p in plots.values()), default=0) + 2,
    )
    return plots, standing, (max(reach[0], 60), max(reach[1], math.ceil(reach[0] / 4)))
