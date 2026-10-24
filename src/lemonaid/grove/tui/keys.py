"""What each key does in the grove: digits pick a block, letters a tree, and `/` searches.

`step` is the whole of it: given where the grove is and a key, the next state and, when the
key chose a lemon, its channel. The screen only draws and switches.
"""

import dataclasses
from collections import abc

from ..draw import lemon_list
from ..layout.arrange import Arrangement
from ..model import Block, Lemon, Tree


@dataclasses.dataclass(frozen=True)
class Where:
    block: str = ""  # the zoomed-in block's digit
    digits: str = ""  # digits typed toward a block number
    tree: str = ""  # the letter of a tree whose lemons are being picked by number
    number: str = ""  # digits typed toward one of that tree's lemons
    search: str | None = None  # the search text while searching
    chosen: int = 0  # which search match `enter` takes
    note: str = ""  # a word for the prompt line about the last key
    editing: str = (
        ""  # an edit begun with Alt and a key (`rename`, `snooze`...): choosing its target
    )
    picked_tree: str = ""  # the key of the tree chosen to rename, in the zoomed block
    picked_lemon: str = ""  # the channel of one lemon on it, or "" for the tree's session
    pan: tuple[float, float] = (0.0, 0.0)  # the grove point at the overview's top left, if panned


@dataclasses.dataclass(frozen=True)
class Match:
    block: Block
    tree: Tree
    lemon: Lemon


def matches(blocks: abc.Sequence[Block], text: str) -> list[Match]:
    """Lemons whose Brief-ID, tree or name has *text*; Brief-ID matches first."""
    needle = text.strip().lower()
    if not needle:
        return []

    found = [
        Match(block, tree, lemon)
        for block in blocks
        for tree in block.trees
        for lemon in tree.lemons
        if needle in f"{lemon.brief_id} {tree.key} {lemon.name}".lower()
    ]
    return sorted(found, key=lambda m: needle not in m.lemon.brief_id.lower())


def tree_at(block: Block, arrangement: Arrangement, letter: str) -> Tree | None:
    return next(
        (t for t in block.trees if arrangement.trees[(block.name, t.key)].letter == letter), None
    )


def names(blocks: abc.Iterable[Block], arrangement: Arrangement) -> dict[str, str]:
    """What to type to reach each lemon with a key, by channel: its block's digit, then its key
    on its tree, as `5s`, `5S2` or `5S0a`.
    """
    return {
        lemon.channel: block.digit + key
        for block in blocks
        for tree in block.trees
        for i, lemon in enumerate(tree.lemons)
        if (key := lemon_list.key(tree, arrangement.trees[(block.name, tree.key)].letter, i))
    }


def at_rest(where: Where) -> bool:
    """Whether nothing is zoomed into, typed, picked or noted, wherever the view is panned."""
    return dataclasses.replace(where, pan=(0.0, 0.0)) == Where()


def _block(blocks: abc.Sequence[Block], digit: str) -> Block | None:
    return next((b for b in blocks if b.digit == digit), None)


def _search_step(where: Where, key: str, blocks: abc.Sequence[Block]) -> tuple[Where, str]:
    found = matches(blocks, where.search or "")
    if key == "escape":
        return Where(), ""
    if key == "enter":
        return (Where(), found[where.chosen % len(found)].lemon.channel) if found else (where, "")
    if key == "backspace":
        return dataclasses.replace(where, search=(where.search or "")[:-1], chosen=0), ""
    if key in ("down", "up"):
        step = 1 if key == "down" else -1
        return dataclasses.replace(where, chosen=(where.chosen + step) % max(1, len(found))), ""
    if len(key) == 1:
        return dataclasses.replace(where, search=(where.search or "") + key, chosen=0), ""
    return where, ""


def _number_step(where: Where, key: str, tree: Tree) -> tuple[Where, str]:
    if key == "0" and len(tree.lemons) > 9 and not where.number:
        return dataclasses.replace(where, number="0"), ""

    typed = where.number + key
    index = lemon_list.lemon_index(typed)
    if index is None or index >= len(tree.lemons):
        return dataclasses.replace(where, number="", note=f"no lemon {typed} on this tree"), ""
    return Where(), tree.lemons[index].channel


def step(
    where: Where, key: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> tuple[Where, str]:
    """The state after *key* (a Textual key name or character), and the channel it chose, or ""."""
    if where.search is not None:
        return _search_step(where, key, blocks)

    where = dataclasses.replace(where, note="")
    if key == "escape":
        if where.tree:
            return dataclasses.replace(where, tree="", number=""), ""
        return Where(pan=where.pan), ""
    if key == "slash" or key == "/":
        return Where(search=""), ""

    zoomed = _block(blocks, where.block)
    if key.isdigit() and len(key) == 1:
        if zoomed and where.tree:
            tree = tree_at(zoomed, arrangement, where.tree)
            return _number_step(where, key, tree) if tree else (Where(), "")
        typed = where.digits + key
        if not any(b.digit.startswith(typed) for b in blocks):
            typed = key
        if _block(blocks, typed):
            return Where(block=typed, digits=typed), ""
        return dataclasses.replace(where, digits="", note=f"no block {typed}"), ""

    if where.number and zoomed and len(key) == 1:  # the letter after a lemon's `0`
        tree = tree_at(zoomed, arrangement, where.tree)
        return _number_step(where, key, tree) if tree else (Where(), "")

    if len(key) == 1 and key.isalpha():
        if not zoomed:
            return dataclasses.replace(where, note="type a block number first, or / to search"), ""
        tree = tree_at(zoomed, arrangement, key.lower())
        if tree is None:
            return dataclasses.replace(
                where, note=f"no tree {key.lower()} in {zoomed.name or 'no group'}"
            ), ""
        if key.islower():
            return Where(), tree.lemons[0].channel
        if len(tree.lemons) < 2:
            return dataclasses.replace(where, note="that tree has one lemon"), ""
        return dataclasses.replace(where, tree=key.lower(), number="", digits=""), ""

    return where, ""


def reconcile(where: Where, before: abc.Sequence[Block], after: abc.Sequence[Block]) -> Where:
    """*where* for a refreshed grove: a zoomed block that ended or changed number is let go."""
    if not where.block:
        return where

    old, new = _block(before, where.block), _block(after, where.block)
    if old is None or new is None or old.name != new.name:
        return Where(search=where.search, chosen=where.chosen)
    return where
