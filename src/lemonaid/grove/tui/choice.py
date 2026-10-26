"""What select mode has chosen, read from where the keys have taken the grove."""

import dataclasses
from collections import abc

from ..draw import lemon_list
from ..layout.arrange import Arrangement
from ..model import Block, Lemon, Tree
from . import keys


def chosen(
    where: keys.Where, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> tuple[Block, Tree, Lemon | None] | None:
    """The chosen tree and its block, with the chosen lemon, or None when the whole tree is."""
    block = (
        next((b for b in blocks if b.digit == where.block), None) if where.selected_tree else None
    )
    tree = keys.tree_at(block, arrangement, where.selected_tree) if block else None
    if block is None or tree is None:
        return None

    return block, tree, next((m for m in tree.lemons if m.channel == where.selected_lemon), None)


def typed(where: keys.Where, blocks: abc.Sequence[Block], arrangement: Arrangement) -> str:
    """The choice as its keys, as `5`, `5s`, `5.s1` or `5$s`."""
    found = chosen(where, blocks, arrangement)
    if found is None:
        typing = "." if where.dot else "$" if where.whole else ""
        return where.block + typing + (f".{where.tree}{where.number}" if where.tree else "")

    block, tree, lemon = found
    if lemon is None:
        return f"{block.digit}${where.selected_tree}"
    return block.digit + lemon_list.key(tree, where.selected_tree, tree.lemons.index(lemon))


def reconcile(
    where: keys.Where, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> keys.Where:
    """*where* for a refreshed grove: a chosen tree that went is let go, and a chosen lemon that
    went leaves its tree chosen.
    """
    if not where.selected_tree:
        return where

    found = chosen(where, blocks, arrangement)
    if found is None:
        return dataclasses.replace(where, selected_tree="", selected_lemon="", number="")
    if where.selected_lemon and found[2] is None:
        return dataclasses.replace(where, selected_lemon="")
    return where
