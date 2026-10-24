"""The spot a block's lead stands in: nearest the packhouse, whichever tree holds the lead.

Other trees keep clear of it, and a tree that stops leading goes back to its own spot.
"""

import math
from typing import Any

from ..model import Block, Plot, Tree
from . import labels, new_spots, placement, sizes

# Its key among the block's saved tree spots. No tree's key can start with a colon: tmux
# session names can't hold one, directories start with `/`, and channels with their backend.
KEY = ":lead"


def standing_at(tree: Tree, spots: dict[str, Any]) -> dict[str, Any]:
    return spots[KEY] if tree.lead and KEY in spots else spots[tree.key]


def _free(
    tree: Tree,
    label: str,
    size: float,
    plot: Plot,
    spots: dict[str, Any],
    toward: tuple[float, float],
) -> dict[str, Any]:
    width, height, top = new_spots.footprint(tree, label, labels.LEAD_LETTER, size)
    placed = [
        (
            s["x"] - s.get("w", width) // 2,
            s["y"] - s.get("top", top),
            s.get("w", width),
            s.get("h", height),
        )
        for s in spots.values()
        if not s.get("gone_since") and "x" in s  # the lead's own spot too: it goes back there
    ]
    # A lead never spills: its block grows only for its other trees.
    (x, y), _ = placement.new_spot(plot, [(width, height, top)], placed, toward, squeeze=True)
    return {
        "x": x + width // 2,
        "y": y + top,
        "w": width,
        "h": height,
        "top": top,
        "letter": labels.LEAD_LETTER,
    }


def reserve(
    block: Block,
    lead: Tree,
    short: dict[str, str],
    drawn: dict[str, float],
    plot: Plot,
    spots: dict[str, Any],
    now: float,
    toward: tuple[float, float],
) -> None:
    """Set the lead spot, once: free ground nearest the packhouse, or, when another tree stands
    nearer, that tree's spot, the tree moving to fresh ground and keeping its letter.
    """
    free = _free(lead, short[lead.key], drawn[lead.key], plot, spots, toward)

    def away(spot: dict[str, Any]) -> float:
        return math.hypot(spot["x"] - toward[0], (spot["y"] - toward[1]) * 2)

    width, height, top = new_spots.footprint(
        lead, short[lead.key], labels.LEAD_LETTER, drawn[lead.key]
    )

    nearer = min(
        (t for t in block.trees if not t.lead and away(spots[t.key]) < away(free)),
        key=lambda t: away(spots[t.key]),
        default=None,
    )
    if nearer is None:
        spots[KEY] = free
        return

    taken = spots[nearer.key]
    spots[KEY] = {
        **taken,
        "x": min(max(taken["x"], width // 2), plot.w - (width - width // 2)),
        "y": min(max(taken["y"], 0), plot.h - (height - top)),
        "w": width,
        "h": height,
        "top": top,
        "letter": labels.LEAD_LETTER,
        "gone_since": None,
    }
    others = {k: v for k, v in spots.items() if k != nearer.key}
    spots[nearer.key] = {
        **new_spots.new_spot(
            nearer, short[nearer.key], sizes.SMALLEST, plot, others, now, reuse=False
        ),
        "letter": spots[nearer.key]["letter"],
        "moved": True,
    }
