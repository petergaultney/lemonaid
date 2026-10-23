"""Picking a tree or one of its lemons with Alt and its key, and renaming what is picked.

Alt with a tree's letter picks the whole tree, and Alt with the capital its second lemon; with
a tree picked, a digit picks its lemon of that number. `r` renames what is picked: a tree's
tmux session, or a lemon's display name.
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


def _unpicked(where: keys.Where) -> keys.Where:
    return dataclasses.replace(where, picked_tree="", picked_lemon="", number="")


def _pick(
    where: keys.Where, key: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> keys.Where:
    block = next((b for b in blocks if b.digit == where.block), None)
    if block is None:
        return dataclasses.replace(where, note="type a block number first, then Alt and a letter")

    letter = key.removeprefix("alt+").removeprefix("shift+")
    tree = keys.tree_at(block, arrangement, letter)
    if tree is None:
        return dataclasses.replace(where, note=f"no tree {letter} in {block.name or 'no group'}")
    if not key.startswith("alt+shift+"):
        return dataclasses.replace(_unpicked(where), picked_tree=tree.key)
    if len(tree.lemons) < 2:
        return dataclasses.replace(where, note="that tree has one lemon")
    return dataclasses.replace(
        _unpicked(where), picked_tree=tree.key, picked_lemon=tree.lemons[1].channel
    )


def _number(where: keys.Where, key: str, tree: Tree) -> keys.Where:
    """Pick by number, a digit at a time: `1` picks lemon 1 and, on a tree of ten or more,
    waits for a `0` that makes it lemon 10.
    """

    def fits(typed: str) -> bool:
        return typed.isdigit() and 1 <= int(typed) <= len(tree.lemons)

    typed = where.number + key if fits(where.number + key) else key
    if not fits(typed):
        return dataclasses.replace(where, number="", note=f"no lemon {key} on this tree")

    longer = any(str(i).startswith(typed) for i in range(int(typed) * 10, len(tree.lemons) + 1))
    return dataclasses.replace(
        where, picked_lemon=tree.lemons[int(typed) - 1].channel, number=typed if longer else ""
    )


def step(
    where: keys.Where, key: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> tuple[keys.Where, str, Rename | None]:
    """`keys.step`, with picking on top; also the rename `r` asked for, if it did."""
    where = dataclasses.replace(where, note="")
    if key.startswith("alt+") and len(key.removeprefix("alt+").removeprefix("shift+")) == 1:
        return _pick(where, key, blocks, arrangement), "", None

    found = _picked(where, blocks)
    if found is None:
        return (*keys.step(_unpicked(where), key, blocks, arrangement), None)

    _, tree = found
    if key == "escape":
        return _unpicked(where), "", None
    if key == "enter":
        lemon = _lemon(tree, where.picked_lemon) or tree.lemons[0]
        return keys.Where(), lemon.channel, None
    if key.isdigit() and len(key) == 1:
        return _number(where, key, tree), "", None
    if key == "r":
        lemon = _lemon(tree, where.picked_lemon)
        if lemon is None and not renames_session(tree):
            return (
                dataclasses.replace(
                    where, note="only a tmux session can be renamed; pick one of its lemons"
                ),
                "",
                None,
            )
        same = [(b, t) for b in blocks for t in b.trees if t.key == tree.key]
        current = lemon.name if lemon else tree.key
        rename = Rename(
            tuple(b.name for b, _ in same),
            tree.key,
            where.picked_lemon,
            current,
            tuple((m.channel, m.window) for _, t in same for m in t.lemons),
        )
        return where, "", rename
    return (*keys.step(_unpicked(where), key, blocks, arrangement), None)


def prompt(where: keys.Where, blocks: abc.Sequence[Block], letter: str) -> str:
    """The prompt line while something is picked, or "" when nothing is."""
    found = _picked(where, blocks)
    if found is None:
        return ""

    _, tree = found
    lemon = _lemon(tree, where.picked_lemon)
    what = f"lemon {lemon.brief_id or lemon.name}" if lemon else f"session {tree.key}"
    numbers = f" · 1-{len(tree.lemons)} picks a lemon" if len(tree.lemons) > 1 else ""
    return f"{where.block}{letter} {what} picked · r renames{numbers} · enter jumps · esc lets go"
