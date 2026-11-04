"""What a key, as `5e` or `5.e2`, reaches: the keys the inbox and the grove show, so a lemon
can read one the person types to it.
"""

import dataclasses
from collections import abc

from ..grove.layout.arrange import Arrangement
from ..grove.model import Block, Lemon, Tree
from ..grove.tui import keys


@dataclasses.dataclass(frozen=True)
class Keyed:
    key: str  # what reaches this lemon, as `5e` or `5.e2`; "" for one reached only by search
    tree_key: str  # what reaches its tree's main lemon, as `5e`
    block: Block
    tree: Tree
    lemon: Lemon


def every(blocks: abc.Iterable[Block], arrangement: Arrangement) -> list[Keyed]:
    blocks = tuple(blocks)
    own = keys.names(blocks, arrangement)
    return [
        Keyed(
            own.get(lemon.channel, ""),
            block.digit + arrangement.trees[(block.name, tree.key)].letter,
            block,
            tree,
            lemon,
        )
        for block in blocks
        for tree in block.trees
        for lemon in tree.lemons
    ]


def resolve(everything: abc.Iterable[Keyed], typed: str) -> list[Keyed]:
    """The lemons *typed* names: a tree's key names all its lemons, main one first; a dotted
    key, one lemon; a block's digit, the whole block.
    """
    typed = typed.strip().lower()
    everything = list(everything)
    return (
        [k for k in everything if k.tree_key == typed]
        or [k for k in everything if k.key == typed]
        or [k for k in everything if k.block.digit == typed]
    )
