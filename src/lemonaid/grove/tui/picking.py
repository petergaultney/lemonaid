"""Renaming from the grove: Alt+r, then a tree's letter, then which of its names.

The tree's letter chooses its tmux session first; the letter again, or an arrow, moves on to each
of its lemons in turn, and Enter asks for the new name. It is slower than a key a lemon, on
purpose: renaming is rare, and what is about to be renamed is always shown before it happens.
"""

import dataclasses
from collections import abc

from ..layout.arrange import Arrangement
from ..model import Block, Lemon, Tree
from . import keys


@dataclasses.dataclass(frozen=True)
class Rename:
    groups: tuple[str, ...]  # every group with a tree for the session, "" for the packhouse
    tree: str  # the tree's key, which is its tmux session
    channel: str  # the lemon to rename, or "" for the tree's session
    name: str  # asked for with the current name, which the rename dialog replaces
    lemons: tuple[tuple[str, str], ...]  # (channel, window) of each lemon in the session


def _picked(where: keys.Where, blocks: abc.Sequence[Block]) -> tuple[Block, Tree] | None:
    block = next((b for b in blocks if b.digit == where.block), None)
    tree = next((t for t in block.trees if t.key == where.picked_tree), None) if block else None
    return (block, tree) if block and tree else None


def _lemon(tree: Tree, channel: str) -> Lemon | None:
    return next((lemon for lemon in tree.lemons if lemon.channel == channel), None)


def renames_session(tree: Tree) -> bool:
    return bool(tree.lemons) and tree.lemons[0].session == tree.key


def _choices(tree: Tree) -> list[str]:
    """What can be renamed on *tree*, in turn: its session, "", if it is one, then each lemon."""
    return [*([""] if renames_session(tree) else []), *(lemon.channel for lemon in tree.lemons)]


def _let_go(where: keys.Where) -> keys.Where:
    return dataclasses.replace(where, renaming=False, picked_tree="", picked_lemon="")


def _choose_tree(
    where: keys.Where, letter: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> keys.Where:
    block = next((b for b in blocks if b.digit == where.block), None)
    if block is None:
        return dataclasses.replace(where, note="type a block number, then a tree's letter")

    tree = keys.tree_at(block, arrangement, letter)
    if tree is None:
        return dataclasses.replace(where, note=f"no tree {letter} in {block.name or 'no group'}")
    return dataclasses.replace(where, picked_tree=tree.key, picked_lemon=_choices(tree)[0])


def _turn(where: keys.Where, tree: Tree, by: int) -> keys.Where:
    choices = _choices(tree)
    at = choices.index(where.picked_lemon) if where.picked_lemon in choices else 0
    return dataclasses.replace(where, picked_lemon=choices[(at + by) % len(choices)])


def _rename(where: keys.Where, blocks: abc.Sequence[Block], tree: Tree) -> Rename:
    lemon = _lemon(tree, where.picked_lemon)
    same = [(b, t) for b in blocks for t in b.trees if t.key == tree.key]
    return Rename(
        tuple(b.name for b, _ in same),
        tree.key,
        where.picked_lemon,
        lemon.name if lemon else tree.key,
        tuple((m.channel, m.window) for _, t in same for m in t.lemons),
    )


def _renaming_step(
    where: keys.Where, key: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> tuple[keys.Where, str, Rename | None]:
    if key == "escape":
        return _let_go(where), "", None
    if key.isdigit() and len(key) == 1 and not where.picked_tree:
        found, _ = keys.step(dataclasses.replace(where, renaming=False), key, blocks, arrangement)
        return dataclasses.replace(found, renaming=True), "", None

    found = _picked(where, blocks)
    letter = key.lower() if len(key) == 1 and key.isalpha() else ""
    if found:
        block, tree = found
        if letter and letter == arrangement.trees[(block.name, tree.key)].letter:
            return _turn(where, tree, 1), "", None
        if key in ("down", "right", "tab"):
            return _turn(where, tree, 1), "", None
        if key in ("up", "left", "shift+tab"):
            return _turn(where, tree, -1), "", None
        if key == "enter":
            return where, "", _rename(where, blocks, tree)
    if letter:
        return _choose_tree(where, letter, blocks, arrangement), "", None
    return where, "", None


def step(
    where: keys.Where, key: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> tuple[keys.Where, str, Rename | None]:
    """`keys.step`, with renaming on top; also the rename Enter asked for, if it did."""
    where = dataclasses.replace(where, note="")
    if key == "alt+r" and where.search is None:
        return dataclasses.replace(_let_go(where), renaming=True), "", None
    if where.renaming:
        return _renaming_step(where, key, blocks, arrangement)
    return (*keys.step(where, key, blocks, arrangement), None)


def prompt(where: keys.Where, blocks: abc.Sequence[Block], letter: str) -> str:
    """The prompt line while renaming, or "" when not."""
    if not where.renaming:
        return ""

    found = _picked(where, blocks)
    if found is None:
        first = "a tree's letter" if where.block else "a block number, then a tree's letter"
        return f"rename: type {first} · esc cancels"

    _, tree = found
    lemon = _lemon(tree, where.picked_lemon)
    what = f"lemon {lemon.brief_id or lemon.name}" if lemon else f"tmux session {tree.key}"
    more = (
        f" · {letter} or ↑↓ for the next of {len(_choices(tree))}"
        if len(_choices(tree)) > 1
        else ""
    )
    return f"rename {what}?{more} · enter renames · esc cancels"
