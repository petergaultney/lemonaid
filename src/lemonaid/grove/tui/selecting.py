"""Select mode: keys choose a block, a tree or a lemon without jumping to it, and single letters
edit the choice.

The choosing follows the jump grammar, `5` a block, `5s` a tree's first lemon and `5.s1` another
lemon on it, and `5$s` chooses the whole tree. Zoomed into a block with nothing chosen, a letter
chooses a tree; a block is recolored through any of its trees' `c`.
"""

import dataclasses
from collections import abc

from ..draw import lemon_list
from ..layout.arrange import Arrangement
from ..model import Block, Lemon, Tree
from . import choice, keys, picking

VERBS = {"r": "rename", "s": "snooze", "a": "archive", "p": "pin", "g": "group", "c": "color"}
DEFAULT_KEY = "tab"

Step = tuple[keys.Where, str, picking.Target | None]


def _block(blocks: abc.Sequence[Block], digit: str) -> Block | None:
    return next((b for b in blocks if b.digit == digit), None)


def _cleared(where: keys.Where) -> keys.Where:
    return dataclasses.replace(
        where, selected_tree="", selected_lemon="", dot=False, whole=False, tree="", number=""
    )


def _noted(where: keys.Where, note: str) -> Step:
    return dataclasses.replace(where, note=note), "", None


def _back(where: keys.Where) -> keys.Where:
    """Half-typed keys undone, else the choice, back to its block, else the block."""
    if where.number:
        return dataclasses.replace(where, number="")
    if where.dot or where.whole or where.tree or where.selected_tree:
        return _cleared(where)
    return keys.Where(selecting=True, pan=where.pan)


def _lemon_number(where: keys.Where, key: str, tree: Tree) -> Step:
    """The place typed after a dot and a tree's letter, as `.s1`: 1 to 9, or 0 and a letter."""
    if key == "0" and len(tree.lemons) > 10 and not where.number:
        return dataclasses.replace(where, number="0"), "", None

    number = where.number + key
    index = lemon_list.lemon_index(number)
    if index is None or index >= len(tree.lemons):
        return _noted(dataclasses.replace(where, number=""), f"no lemon {number} on this tree")
    return (
        dataclasses.replace(
            _cleared(where), selected_tree=where.tree, selected_lemon=tree.lemons[index].channel
        ),
        "",
        None,
    )


def _neighbor(where: keys.Where, tree: Tree, lemon: Lemon, by: int) -> keys.Where:
    """The lemon *by* places along *tree*'s list from *lemon*, stopping at either end."""
    at = min(max(0, tree.lemons.index(lemon) + by), len(tree.lemons) - 1)
    return dataclasses.replace(where, selected_lemon=tree.lemons[at].channel)


def _edit(
    where: keys.Where,
    verb: str,
    blocks: abc.Sequence[Block],
    found: tuple[Block, Tree, Lemon | None],
) -> Step:
    block, tree, lemon = found
    action = VERBS[verb]
    if action == "color":
        if not block.name:
            return _noted(where, "the packhouse has no color")
        editing = dataclasses.replace(where, editing=action)
        return editing, "", picking.target(editing, blocks, block, None)

    whole = "" in picking.edit_choices(action, tree)  # not a one-lemon tree, or a dir's rename
    channel = lemon.channel if lemon else "" if whole else tree.lemons[0].channel
    editing = dataclasses.replace(where, editing=action, picked_tree=tree.key, picked_lemon=channel)
    return editing, "", picking.target(editing, blocks, block, tree)


def _searched(
    where: keys.Where, key: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> Step:
    """A search that chooses its match rather than jumping to it."""
    if key == "escape":
        return keys.Where(selecting=True, pan=where.pan), "", None
    found = keys.matches(blocks, where.search or "")
    if key == "enter" and found:
        match = found[where.chosen % len(found)]
        letter = arrangement.trees[(match.block.name, match.tree.key)].letter
        return (
            keys.Where(
                block=match.block.digit,
                pan=where.pan,
                selecting=True,
                selected_tree=letter,
                selected_lemon=match.lemon.channel,
            ),
            "",
            None,
        )
    where, _ = keys.step(where, key, blocks, arrangement)
    return where, "", None


def _letter(
    where: keys.Where, key: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> Step:
    zoomed = _block(blocks, where.block)
    if zoomed is None:
        return _noted(where, "type a block number first, or / to search")
    if where.dot or where.whole:
        tree = keys.tree_at(zoomed, arrangement, key) if key.islower() else None
        sigil = "a dot" if where.dot else "$"
        if tree is None:
            return _noted(_cleared(where), f"{sigil} takes a tree's letter")
        if where.whole:
            return dataclasses.replace(_cleared(where), digits="", selected_tree=key), "", None
        if len(tree.lemons) < 2:
            return _noted(_cleared(where), "that tree has one lemon: its letter alone chooses it")
        return dataclasses.replace(_cleared(where), digits="", tree=key), "", None
    tree = keys.tree_at(zoomed, arrangement, where.tree) if where.tree else None
    if tree and where.number:  # the letter after a place's `0`
        return _lemon_number(where, key, tree)
    if where.tree:
        return _noted(where, "type the lemon's place on the tree")

    found = choice.chosen(where, blocks, arrangement)
    if found and key == "o":
        return where, (found[2] or found[1].lemons[0]).channel, None
    if found and key in VERBS:
        return _edit(where, key, blocks, found)
    if found:
        return _noted(where, "r s a p g c edit · o jumps · backspace to choose another tree")
    if key.isupper():
        return _noted(where, "$ and a tree's letter chooses the whole tree")

    return choose_tree(where, key, blocks, arrangement), "", None


def choose_tree(
    where: keys.Where, letter: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> keys.Where:
    """*where* with the first lemon on the zoomed block's tree *letter* chosen, as a click on a
    tree chooses it in select mode, whatever was chosen before.
    """
    zoomed = _block(blocks, where.block)
    tree = keys.tree_at(zoomed, arrangement, letter) if zoomed else None
    if zoomed is None or tree is None:
        return dataclasses.replace(where, note=f"no tree {letter} here")

    return dataclasses.replace(
        _cleared(where), digits="", selected_tree=letter, selected_lemon=tree.lemons[0].channel
    )


def _choosing(
    where: keys.Where, key: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> Step:
    if key == "escape":
        return keys.Where(block=where.block, digits=where.block, pan=where.pan), "", None
    if key == "backspace":
        return _back(where), "", None
    if key in ("slash", "/"):
        return keys.Where(search="", pan=where.pan, selecting=True), "", None

    found = choice.chosen(where, blocks, arrangement)
    if key == "enter":
        if found is None:
            return _noted(where, "choose a tree or a lemon to jump to")
        return where, (found[2] or found[1].lemons[0]).channel, None
    if key in (".", "$"):
        if not _block(blocks, where.block):
            return _noted(where, "type a block number first, or / to search")
        return (
            dataclasses.replace(_cleared(where), dot=key == ".", whole=key == "$", digits=""),
            "",
            None,
        )
    if key in ("up", "down") and found and found[2]:
        return _neighbor(where, found[1], found[2], 1 if key == "down" else -1), "", None

    single = len(key) == 1
    zoomed = _block(blocks, where.block)
    if where.tree and zoomed and single and key.isdigit():
        tree = keys.tree_at(zoomed, arrangement, where.tree)
        return _lemon_number(where, key, tree) if tree else (_cleared(where), "", None)
    if single and key.isdigit():
        jumped, _ = keys.step(
            _cleared(dataclasses.replace(where, selecting=False)), key, blocks, arrangement
        )
        return dataclasses.replace(jumped, selecting=True, pan=where.pan), "", None
    if single and key.isalpha():
        return _letter(where, key, blocks, arrangement)
    return where, "", None


def step(
    where: keys.Where,
    key: str,
    blocks: abc.Sequence[Block],
    arrangement: Arrangement,
    select_key: str = DEFAULT_KEY,
) -> Step:
    """`keys.step`, with select mode on top: *select_key* enters it, and again or `esc` leaves."""
    where = dataclasses.replace(where, note="")
    if key == select_key and not where.editing and where.search is None:
        if where.selecting:
            return keys.Where(block=where.block, digits=where.block, pan=where.pan), "", None
        return (
            dataclasses.replace(where, selecting=True, dot=False, whole=False, tree="", number=""),
            "",
            None,
        )
    if where.editing:  # its dialog has the keys; the grove waits for it to finish
        return where, "", None
    if where.search is not None and where.selecting:
        return _searched(where, key, blocks, arrangement)
    if where.selecting and where.search is None:
        return _choosing(where, key, blocks, arrangement)
    return (*keys.step(where, key, blocks, arrangement), None)
