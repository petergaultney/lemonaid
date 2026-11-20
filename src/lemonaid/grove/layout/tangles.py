"""Whether a laid-out block's trees stand where their saved spots put them, clear of each other."""

import dataclasses
from collections import abc
from typing import Any

from ..draw import ground
from ..model import Block, Tree
from . import arrange, edit, footing, lead_spot, placement, room, sizes


def _footprints(
    block: Block, arrangement: arrange.Arrangement
) -> list[tuple[Tree, placement.Rect]]:
    oldest_first = sorted(block.trees, key=lambda t: (not t.lead, t.born, t.key))
    # At their smallest, as the layout judges it: trees near each other shrink to fit.
    return [
        (t, room.footprint(t, s.label, s.letter, sizes.SMALLEST, s.cx, s.cy))
        for t in oldest_first
        for s in [arrangement.trees[(block.name, t.key)]]
    ]


def tangled(block: Block, arrangement: arrange.Arrangement) -> list[Tree]:
    return [tree for tree, _ in room.tangled(_footprints(block, arrangement))]


def in_the_way(block: Block, arrangement: arrange.Arrangement, key: str) -> str:
    """The tree *key* would stand on, as a refusal, or "" when it stands clear."""
    footprints = _footprints(block, arrangement)
    moved = next(f for f in footprints if f[0].key == key)
    return next(
        (
            f"tree {arrangement.trees[(block.name, other.key)].letter} stands there"
            for other, rect in footprints
            if other.key != key and room.tangled([(other, rect), moved])
        ),
        "",
    )


def refusal(block: Block, arrangement: arrange.Arrangement, key: str) -> str:
    """Why tree *key* can't stand where *arrangement* has it, or "" when it can: the rule a drag,
    a drop and a gardening lemon all follow, so a tree stood where it passes stays there.
    """
    tree = next(t for t in block.trees if t.key == key)
    s = arrangement.trees[(block.name, key)]
    plot = arrangement.plots[block.name]
    return footing.refusal(tree, plot, s.cx, s.cy) or in_the_way(block, arrangement, key)


def refusal_at(block: Block, arrangement: arrange.Arrangement, key: str, x: int, y: int) -> str:
    """`refusal` for tree *key* moved to (*x*, *y*) in its plot, as a drag previews a drop."""
    standing = arrangement.trees[(block.name, key)]
    moved = {**arrangement.trees, (block.name, key): dataclasses.replace(standing, cx=x, cy=y)}
    return refusal(block, dataclasses.replace(arrangement, trees=moved), key)


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
    stand anywhere but that spot, or where `refusal` turns it down, or if *after* would tangle a
    tree that *before* left clear, or push a tree whose spot didn't change from it, or leave one
    that stood on its block's ground off the block's new shape. The packhouse, which stands its bays
    in order, isn't checked.
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
            if moved and "x" in spot:
                asked = dataclasses.replace(s, cx=spot["x"], cy=spot["y"])
                stood = dataclasses.replace(now, trees={**now.trees, (block.name, tree.key): asked})
                problem = refusal(block, stood, tree.key)
                if not problem and (s.cx, s.cy) != (asked.cx, asked.cy):
                    problem = "the grove would move it from there"
                if problem:
                    raise edit.EditError(
                        f"{block.name or 'the ungrouped block'}: tree {s.letter} can't stand at "
                        f"{spot['x']},{spot['y']}: {problem}"
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


def plant(
    blocks: tuple[Block, ...],
    saved: dict[str, Any],
    block: Block,
    spots: dict[str, tuple[int, int]],
) -> dict[str, Any]:
    """*saved* with each of *block*'s trees in *spots* (by key) standing at its (x, y), for
    `state.update`; raises EditError, changing nothing, where `check` refuses it.
    """
    changed = saved
    for tree in block.trees:
        if tree.key in spots:
            changed = edit.place_tree(changed, block.name, tree.key, tree.lead, *spots[tree.key])
    check(blocks, saved, changed, {block.name})
    return changed
