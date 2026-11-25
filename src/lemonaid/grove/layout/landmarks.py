"""The grove's fixed features: the packhouse at its middle, its roads, and a stream.

The packhouse, when it's on, holds the lemons in no group (HQ among them); when it's off they
are an ordinary block. Roads and the stream are saved with the layout once laid, so they never
move; blocks are drawn over them, so they show in the gaps, and a road crosses the stream on a
bridge.
"""

import dataclasses
from collections import abc
from typing import Any

from ..model import WORLD_HEIGHT, WORLD_WIDTH, Plot
from . import placement

PACKHOUSE = ""  # the block name of lemons in no group
_WIDTH = 24


def has_house(saved: abc.Mapping[str, Any]) -> bool:
    """Whether the lemons in no group stand in the packhouse in saved layout *saved*; a layout
    from before the packhouse could be turned off has it.
    """
    return bool(saved.get("packhouse", True))


def with_packhouse(saved: dict[str, Any], on: bool) -> dict[str, Any]:
    """*saved* with the lemons in no group in the packhouse, or in an ordinary block. Block 0's
    plot and tree spots for the other way are kept under `aside`, so switching back restores them.
    """
    if has_house(saved) == on:
        return {**saved, "packhouse": on}

    plots, trees = dict(saved.get("plots", {})), dict(saved.get("trees", {}))
    leaving = {"plot": plots.pop(PACKHOUSE, None), "trees": trees.pop(PACKHOUSE, None)}
    aside = saved.get("aside", {})
    if aside.get("plot") is not None:
        plots[PACKHOUSE] = aside["plot"]
    if aside.get("trees") is not None:
        trees[PACKHOUSE] = aside["trees"]
    kept = {k: v for k, v in leaving.items() if v is not None}
    rest = {k: v for k, v in saved.items() if k != "aside"}
    return {**rest, "plots": plots, "trees": trees, "packhouse": on} | (
        {"aside": kept} if kept else {}
    )


def as_drawn(saved: dict[str, Any], drawn: abc.Mapping[str, Any]) -> dict[str, Any]:
    """*saved*, read under the layout's lock, with or without the packhouse as layout *drawn*
    has it, so a change made on what was drawn is saved in the same mode.
    """
    return with_packhouse(saved, has_house(drawn))


def middle(house: abc.Mapping[str, Any] | None) -> tuple[float, float] | None:
    """What blocks gather around and leads stand nearest, given block 0's plot as saved: the
    packhouse's middle, or the grove's middle when block 0 is an ordinary block; None without one.
    """
    if house is None:
        return None
    if house.get("texture") != "house":
        return WORLD_WIDTH / 2, WORLD_HEIGHT / 2

    return house["x"] + house["w"] / 2, house["y"] + house["h"] / 2


def gathering(saved: abc.Mapping[str, Any]) -> tuple[float, float] | None:
    """`middle` for a whole saved layout, which knows when the packhouse is off even while
    block 0 has no plot.
    """
    found = middle(saved["plots"].get(PACKHOUSE))
    return found or (None if has_house(saved) else (WORLD_WIDTH / 2, WORLD_HEIGHT / 2))


def packhouse(sessions: int, taken: abc.Sequence[placement.Rect]) -> Plot:
    """A small square building at the grove's middle, or as near it as the blocks allow."""
    height = max(7, 3 + 2 * sessions)
    found = placement.new_plot("packhouse", (_WIDTH, height), taken)
    return dataclasses.replace(found, roundness=12.0, texture="house")


def default_roads() -> list[list[list[int]]]:
    """Three roads to the packhouse: one in from the west edge, one down from the north edge,
    and one from it south, over the stream, past the south edge.
    """
    return [
        [[0, 20], [40, 19], [80, 20], [116, 19]],
        [[122, 0], [120, 12], [118, 24], [113, 28], [108, 32]],
        [[108, 35], [106, 40], [104, 46], [104, 72]],
    ]


def default_stream() -> list[list[int]]:
    """A stream meandering west to east across the grove, a little south of its middle."""
    return [
        [0, 42],
        [20, 44],
        [40, 43],
        [60, 45],
        [80, 44],
        [100, 46],
        [120, 44],
        [140, 45],
        [160, 47],
        [180, 45],
        [200, 46],
        [212, 46],
    ]
