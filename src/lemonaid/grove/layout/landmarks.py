"""The grove's fixed features: the packhouse at its middle, its roads, and a stream.

The packhouse holds the lemons in no group (HQ among them). Roads and the stream are saved
with the layout once laid, so they never move; blocks are drawn over them, so they show in
the gaps, and a road crosses the stream on a bridge.
"""

import dataclasses
import math
from collections import abc

from ..model import WORLD_HEIGHT, WORLD_WIDTH, Plot
from . import placement

PACKHOUSE = ""  # the block name of lemons in no group
_WIDTH = 24


def packhouse(sessions: int, taken: abc.Sequence[placement.Rect]) -> Plot:
    """A small square building at the grove's middle, or as near it as the blocks allow."""
    height = max(7, 3 + 2 * sessions)
    found = placement.new_plot("packhouse", (_WIDTH, height), taken)
    return dataclasses.replace(found, roundness=12.0, texture="house")


def default_roads() -> list[list[list[int]]]:
    """Two roads that cross at the packhouse, each with a bend or two."""
    cx, cy = WORLD_WIDTH // 2, WORLD_HEIGHT // 2
    return [
        [[0, cy - 3], [cx // 2, cy - 1], [cx, cy], [cx + cx // 2, cy + 2], [WORLD_WIDTH, cy]],
        [[cx - 6, 0], [cx - 2, cy // 2], [cx, cy], [cx + 3, cy + cy // 2], [cx + 1, WORLD_HEIGHT]],
    ]


def default_stream() -> list[list[int]]:
    """A stream meandering across the middle, mostly east to west, drifting a little south."""
    points = []
    for step in range(0, 13):
        x = WORLD_WIDTH * step // 12
        drift = -6 + 12 * step / 12
        points.append([x, round(WORLD_HEIGHT / 2 + drift + 4 * math.sin(step * 1.3))])
    return points
