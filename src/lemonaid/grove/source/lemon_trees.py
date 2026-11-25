"""Blocks for trees scale, where a group is one tree and each of its lemons has a letter.

Each lemon becomes a tree of its own, so the keys, the lists and the edits that work on trees
work on lemons. A session's main lemon keeps its session's tree key, and with it the letter that
session has in blocks scale; any other lemon is keyed by its channel.
"""

from collections import abc

from ..model import Block, Tree


def _split(tree: Tree) -> abc.Iterator[Tree]:
    for i, lemon in enumerate(tree.lemons):
        yield Tree(
            tree.key if i == 0 else lemon.channel,
            lemon.name,
            (lemon,),
            tree.lead and i == 0,
            tree.key,
        )


def one_per_lemon(found: abc.Iterable[Block]) -> tuple[Block, ...]:
    """*found* with each lemon a tree named as the inbox names it, its session's lemons together
    and in their order, the lead's session first.
    """
    return tuple(
        Block(
            block.name,
            block.digit,
            block.color,
            tuple(
                t
                for tree in sorted(block.trees, key=lambda tree: not tree.lead)
                for t in _split(tree)
            ),
        )
        for block in found
    )
