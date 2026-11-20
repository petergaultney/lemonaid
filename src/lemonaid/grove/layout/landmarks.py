"""The grove's fixed features: the packhouse at its middle, its roads, and a stream.

The packhouse holds the lemons in no group (HQ among them). Roads and the stream are saved
with the layout once laid, so they never move; blocks are drawn over them, so they show in
the gaps, and a road crosses the stream on a bridge.
"""

import dataclasses
from collections import abc

from ..model import Plot
from . import placement

PACKHOUSE = ""  # the block name of lemons in no group
_WIDTH = 24


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
