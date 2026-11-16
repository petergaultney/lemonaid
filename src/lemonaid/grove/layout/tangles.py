"""Whether a laid-out block's trees stand where their saved spots put them, clear of each other."""

from collections import abc
from typing import Any

from ..draw import ground
from ..model import Block, Tree
from . import arrange, edit, lead_spot, room, sizes


def tangled(block: Block, arrangement: arrange.Arrangement) -> list[Tree]:
    oldest_first = sorted(block.trees, key=lambda t: (not t.lead, t.born, t.key))
    # At their smallest, as the layout judges it: trees near each other shrink to fit.
    footprints = (
        (t, room.footprint(t, s.label, s.letter, sizes.SMALLEST, s.cx, s.cy))
        for t in oldest_first
        for s in [arrangement.trees[(block.name, t.key)]]
    )
    return [tree for tree, _ in room.tangled(footprints)]


def spot_key(spots: dict[str, Any], tree: Tree) -> str:
    """The key *tree*'s saved spot is under: a lead tree stands at its block's lead spot."""
    return lead_spot.KEY if tree.lead and lead_spot.KEY in spots else tree.key


def check(
    blocks: abc.Iterable[Block],
    before: dict[str, Any],
    after: dict[str, Any],
    groups: abc.Container[str],
) -> None:
    """Raise EditError, naming the tree, if a tree in *groups* whose spot *after* changed would
    stand anywhere but that spot, or off its block's rounded ground, or if *after* would tangle a
    tree that *before* left clear, or push a tree whose spot didn't change from it, or leave one
    that stood on its block's ground off the block's new shape, or move a block's lead farther
    from the packhouse. The packhouse,
    which stands its bays in order, isn't checked.
    """
    blocks = tuple(blocks)
    was, now = arrange.arrange(blocks, before)[0], arrange.arrange(blocks, after)[0]
    for block in blocks:
        plot = now.plots.get(block.name)
        if block.name not in groups or block.name not in after["trees"] or plot is None:
            continue
        if plot.texture == "house":
            continue

        spots, kept = after["trees"][block.name], before["trees"].get(block.name, {})
        for tree in block.trees:
            key = spot_key(spots, tree)
            spot, s = spots.get(key, {}), now.trees[(block.name, tree.key)]
            was_at = kept.get(key, {})
            moved = (spot.get("x"), spot.get("y")) != (was_at.get("x"), was_at.get("y"))
            if (
                moved
                and "x" in spot
                and (
                    (s.cx, s.cy) != (spot["x"], spot["y"])
                    or not ground.inside(plot, plot.x + s.cx, plot.y + s.cy)
                )
            ):
                raise edit.EditError(
                    f"{block.name or 'the ungrouped block'}: tree {s.letter} can't stand at "
                    f"{spot['x']},{spot['y']}: it would be off its block's ground or on another tree"
                )
            if moved and key == lead_spot.KEY and "x" in spot and "x" in was_at:
                far = lead_spot.from_packhouse(after, block.name, spot["x"], spot["y"])
                near = lead_spot.from_packhouse(before, block.name, was_at["x"], was_at["y"])
                if far is not None and near is not None and far > near:
                    raise edit.EditError(
                        f"{block.name}: tree {s.letter} leads the block, so it stands nearest "
                        "the packhouse; plant it nearer the packhouse, not farther"
                    )
            old_plot, w = was.plots.get(block.name), was.trees.get((block.name, tree.key))
            if (
                not moved
                and "x" in spot
                and old_plot
                and w
                and ground.inside(old_plot, old_plot.x + w.cx, old_plot.y + w.cy)
                and not ground.inside(plot, plot.x + s.cx, plot.y + s.cy)
            ):
                raise edit.EditError(
                    f"{block.name or 'the ungrouped block'}: tree {s.letter}'s trunk would be "
                    "off the block's new shape; keep its corners squarer, or plant the tree "
                    "inward first"
                )
            if not moved and "x" in spot and (s.cx, s.cy) != (spot["x"], spot["y"]):
                raise edit.EditError(
                    f"{block.name or 'the ungrouped block'}: tree {s.letter} would be pushed "
                    "from its spot by a tree moved onto it"
                )
        old = {t.key for t in tangled(block, was)}
        for tree in tangled(block, now):
            if tree.key not in old:
                letter = now.trees[(block.name, tree.key)].letter
                raise edit.EditError(
                    f"{block.name or 'the ungrouped block'}: tree {letter} would stand on "
                    "another tree"
                )
