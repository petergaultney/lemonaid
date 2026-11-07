"""Blocks laid out when the gap above and below a road or the stream was two rows, given the
row its narrowing to `terrain.GAP` frees, once.

A block grows into that row only where the old gap held it back, and only onto ground clear of
the terrain and of every other block, so one placed by hand away from them keeps its shape.
"""

from collections import abc
from typing import Any

from . import placement, terrain

_OLD_ROWS = 2  # the `clear` marker the two-row gap left on every block it checked


def _grown(
    ground: terrain.Covered, rect: placement.Rect, others: abc.Sequence[placement.Rect]
) -> placement.Rect:
    x, y, w, h = rect
    # A unit clear of the others, but for one put by hand closer: that one it just mustn't cover.
    gaps = [(other, 0 if placement.overlaps(rect, other, 1) else 1) for other in others]
    for _ in range(_OLD_ROWS - terrain.GAP[1]):
        for row, taller in ((y + h, (x, y, w, h + 1)), (y - 1, (x, y - 1, w, h + 1))):
            held = terrain.crosses_box(ground, (x, row, w, 1), (terrain.GAP[0], _OLD_ROWS))
            if (
                held
                and taller[1] >= 1
                and not terrain.crosses_box(ground, taller, terrain.GAP)
                and not any(placement.overlaps(taller, other, gap) for other, gap in gaps)
            ):
                x, y, w, h = taller
    return x, y, w, h


def regrow(saved: dict[str, Any], ground: terrain.Covered) -> None:
    """Grow every block marked `clear` by the two-row gap into the rows it kept from them, and
    mark it with the gap that holds now. Its trees keep their place on the ground.
    """
    plots = saved["plots"]
    for name in sorted(plots):
        data = plots[name]
        if data.get("clear") != _OLD_ROWS or data.get("texture") == "house":
            continue

        data["clear"] = list(terrain.GAP)
        others = [(d["x"], d["y"], d["w"], d["h"]) for key, d in plots.items() if key != name]
        x, y, w, h = _grown(ground, (data["x"], data["y"], data["w"], data["h"]), others)
        if h == data["h"]:
            continue

        for spot in saved["trees"].get(name, {}).values():
            if "y" in spot:
                spot["y"] += data["y"] - y
        data.update(y=y, h=h)
