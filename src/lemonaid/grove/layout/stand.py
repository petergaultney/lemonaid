"""Where each tree stands in its plot, with its letter and size, keeping what was given before.

A tree that goes leaves a free spot, and the next new tree in its block takes the oldest one.
A tree standing on an older one's ground moves to free ground, keeping its letter.
"""

import dataclasses
from typing import Any

from ..model import Block, Plot
from . import labels, lead_spot, new_spots, room, sizes

_FORGET_SPOTS_AFTER = 30 * 86400


@dataclasses.dataclass(frozen=True)
class Standing:
    cx: int  # the crown's center, relative to the plot
    cy: int
    letter: str  # `l` while the tree holds the group's lead
    label: str
    size: float  # 1 for a grown tree in a roomy block
    bay: int = -1  # its bay in the packhouse, kept while it is gone; -1 in any other block


def _spaced(
    block: Block,
    grown: dict[str, float],
    drawn: dict[str, float],
    spots: dict[str, Any],
    plot: Plot,
) -> dict[str, float]:
    """*drawn* shrunk where trees would grow into each other. Saved spots never move, and a tree
    keeps the size it was last drawn at unless that would crowd it, until it grows older: a
    neighbor losing lemons gives it room it doesn't take, so nothing moves for no benefit.
    """
    positions = {
        t.key: (lead_spot.standing_at(t, spots)["x"], lead_spot.standing_at(t, spots)["y"])
        for t in block.trees
    }
    fitted = sizes.spaced(block, drawn, positions, plot)[0]
    for tree in block.trees:
        spot = spots[tree.key]
        if spot.get("grown") == grown[tree.key] and "size" in spot:
            fitted[tree.key] = min(fitted[tree.key], spot["size"])
        spot["size"], spot["grown"] = fitted[tree.key], grown[tree.key]
    return fitted


def _anchor(
    block: Block, spots: dict[str, Any], toward: tuple[float, float] | None
) -> tuple[float, float] | None:
    """Where a new tree in *block* stands nearest: its lead, else its oldest tree standing, else
    the packhouse (*toward*), so a block's trees keep together.
    """
    standing = [t for t in block.trees if "x" in spots.get(t.key, {})]
    first = next((t for t in standing if t.lead), None) or min(
        standing, key=lambda t: (t.born, t.key), default=None
    )
    if first is None:
        return toward

    at = lead_spot.standing_at(first, spots)
    return at["x"], at["y"]


def _untangle(
    block: Block,
    short: dict[str, str],
    drawn: dict[str, float],
    plot: Plot,
    spots: dict[str, Any],
    now: float,
) -> None:
    oldest_first = sorted(block.trees, key=lambda t: (not t.lead, t.born, t.key))
    # At their smallest: trees that only grow into each other are shrunk apart, not moved.
    for tree, _ in room.tangled(
        (t, room.footprint(t, short[t.key], "x", sizes.SMALLEST, at["x"], at["y"]))
        for t in oldest_first
        for at in [lead_spot.standing_at(t, spots)]
    ):
        letter = spots[tree.key]["letter"]
        others = {k: v for k, v in spots.items() if k != tree.key}
        moved = new_spots.clear_spot(tree, short[tree.key], letter, drawn[tree.key], plot, others)
        if moved is None and not spots[tree.key].get("squeezed"):
            # Past the plot's edge, for the block to grow into; a tree already squeezed into a
            # block that couldn't grow stays where it is.
            moved = new_spots.new_spot(
                tree, short[tree.key], drawn[tree.key], plot, others, now, False
            )
        if moved:
            spots[tree.key] = {**moved, "letter": letter}


def stand_trees(
    block: Block,
    plot: Plot,
    saved: dict[str, Any],
    now: float,
    toward: tuple[float, float] | None = None,
    bays: bool = False,
) -> dict[str, Standing]:
    """Where each of *block*'s trees stands. *toward*, the packhouse relative to the plot's
    corner, is where the block's lead stands nearest; without it the lead keeps its own spot.
    With *bays*, for the packhouse, each tree gets the lowest bay no live tree holds.
    """
    spots: dict[str, Any] = saved["trees"].setdefault(block.name, {})
    live = {tree.key for tree in block.trees} | {lead_spot.KEY}
    for key, spot in spots.items():
        if key in live:
            spot["gone_since"] = None
        elif spot.get("gone_since") is None:
            spot["gone_since"] = now
    for key in [
        k
        for k, s in spots.items()
        if s.get("gone_since") and now - s["gone_since"] > _FORGET_SPOTS_AFTER
    ]:
        del spots[key]

    derived = labels.labels(block.name, [tree.key for tree in block.trees])
    # A tree takes the name given to its main lemon, as the inbox shows it; else its session's.
    short = {
        t.key: labels.without_group(block.name, t.lemons[0].name)
        if t.lemons[0].named
        else derived[t.key]
        for t in block.trees
    }
    grown = {tree.key: sizes.growth(tree.born, now) for tree in block.trees}
    # Kept from the block's first layout, so lemons coming and going never resize its trees.
    crowd = saved["plots"][block.name].setdefault("crowd", sizes.crowding(plot, block, grown))
    drawn = {key: size * crowd for key, size in grown.items()}

    for tree in block.trees:
        if tree.key not in spots:
            spots[tree.key] = new_spots.new_spot(
                tree,
                short[tree.key],
                drawn[tree.key],
                plot,
                spots,
                now,
                toward=_anchor(block, spots, toward),
            )
        elif "x" not in spots[tree.key]:  # given up, to stand afresh in ground its plot grew
            others = {k: v for k, v in spots.items() if k != tree.key}
            spots[tree.key] = {
                **new_spots.new_spot(
                    tree,
                    short[tree.key],
                    drawn[tree.key],
                    plot,
                    others,
                    now,
                    False,
                    _anchor(block, others, toward),
                    squeeze=spots[tree.key].get("squeeze", False),
                ),
                "letter": spots[tree.key]["letter"],
            }
    if bays:
        for tree in block.trees:
            if "bay" not in spots[tree.key]:
                taken = {s["bay"] for s in spots.values() if "bay" in s and not s.get("gone_since")}
                spots[tree.key]["bay"] = next(i for i in range(len(spots) + 1) if i not in taken)
    lead = next((tree for tree in block.trees if tree.lead), None)
    if lead and toward and lead_spot.KEY not in spots:
        lead_spot.reserve(block, lead, short, drawn, plot, spots, now, toward)
    if not bays:
        _untangle(block, short, drawn, plot, spots, now)
    drawn = _spaced(block, grown, drawn, spots, plot)
    standing: dict[str, Standing] = {}
    held: set[str] = set()  # letters live trees in the block already hold
    for tree in block.trees:
        spot = spots[tree.key]
        if (
            spot["letter"] not in labels.LETTERS
            or spot["letter"] in held
            or (spot["letter"] == labels.LEAD_LETTER and not tree.lead)
        ):
            spot["letter"] = labels.pick_letter(
                short[tree.key], {s["letter"] for s in spots.values() if s is not spot}
            )
        held.add(spot["letter"])
        spot["label"] = short[tree.key]  # for its stump to show for a while once it goes
        letter = labels.LEAD_LETTER if tree.lead else spot["letter"]
        stands = lead_spot.standing_at(tree, spots)
        standing[tree.key] = Standing(
            stands["x"], stands["y"], letter, short[tree.key], drawn[tree.key], spot.get("bay", -1)
        )
    return standing
