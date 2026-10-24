"""Editing from the grove: Alt and a key for what to do, then a tree's letter, then which of it.

The tree's letter chooses the whole tree first (for a rename, its tmux session); the letter
again, or an arrow, moves on to each of its lemons in turn, and Enter asks what's needed and does
it. It is slower than a key a lemon, on purpose: edits are rare, and what is about to change is
always named on the prompt line before it does.
"""

import dataclasses
from collections import abc

from ..layout.arrange import Arrangement
from ..model import Block, Lemon, Tree
from . import keys

ACTIONS = {
    "alt+r": "rename",
    "alt+s": "snooze",
    "alt+a": "archive",
    "alt+p": "pin",
    "alt+g": "group",
    "alt+c": "color",
}
_VERBS = {
    "rename": "rename",
    "snooze": "snooze",
    "archive": "archive",
    "pin": "pin or unpin",
    "group": "move to another group",
    "color": "recolor",
}


@dataclasses.dataclass(frozen=True)
class Target:
    action: str  # one of ACTIONS' values
    block: str  # the group it's drawn in, "" for the packhouse
    groups: tuple[str, ...]  # every group with a tree for the session
    tree: str  # the tree's key, which is its tmux session, or "" for a block's color
    channel: str  # the lemon, or "" for the whole tree (for a rename, its session)
    name: str  # the current name, which a rename starts from
    # (channel, window) of each lemon on the tree; for a rename, in its session in every group
    lemons: tuple[tuple[str, str], ...]
    tagged: str = ""  # the lemon whose given name the tree's tag shows, "" when it's the session's


def _picked(where: keys.Where, blocks: abc.Sequence[Block]) -> tuple[Block, Tree] | None:
    block = next((b for b in blocks if b.digit == where.block), None)
    tree = next((t for t in block.trees if t.key == where.picked_tree), None) if block else None
    return (block, tree) if block and tree else None


def _lemon(tree: Tree, channel: str) -> Lemon | None:
    return next((lemon for lemon in tree.lemons if lemon.channel == channel), None)


def renames_session(tree: Tree) -> bool:
    return bool(tree.lemons) and tree.lemons[0].session == tree.key


def _choices(action: str, tree: Tree) -> list[str]:
    """What *action* can act on, in turn: the whole tree, "", where it can, then each lemon."""
    whole = renames_session(tree) if action == "rename" else len(tree.lemons) > 1
    return [*([""] if whole else []), *(lemon.channel for lemon in tree.lemons)]


def _let_go(where: keys.Where) -> keys.Where:
    return dataclasses.replace(where, editing="", picked_tree="", picked_lemon="")


def _target(
    where: keys.Where, blocks: abc.Sequence[Block], block: Block, tree: Tree | None
) -> Target:
    if tree is None:
        return Target(where.editing, block.name, (block.name,), "", "", block.name, ())

    lemon = _lemon(tree, where.picked_lemon)
    same = [(b, t) for b in blocks for t in b.trees if t.key == tree.key]
    return Target(
        where.editing,
        block.name,
        tuple(b.name for b, _ in same),
        tree.key,
        where.picked_lemon,
        lemon.name if lemon else tree.key,
        tuple(
            (m.channel, m.window)
            for t in ([t for _, t in same] if where.editing == "rename" else [tree])
            for m in t.lemons
        ),
        tree.lemons[0].channel if tree.lemons and tree.lemons[0].named else "",
    )


def _choose_tree(
    where: keys.Where, letter: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> keys.Where:
    block = next((b for b in blocks if b.digit == where.block), None)
    if block is None:
        return dataclasses.replace(where, note="type a block number, then a tree's letter")

    tree = keys.tree_at(block, arrangement, letter)
    if tree is None:
        return dataclasses.replace(where, note=f"no tree {letter} in {block.name or 'no group'}")
    first = _choices(where.editing, tree)[0]
    return dataclasses.replace(where, picked_tree=tree.key, picked_lemon=first)


def _turn(where: keys.Where, tree: Tree, by: int) -> keys.Where:
    choices = _choices(where.editing, tree)
    at = choices.index(where.picked_lemon) if where.picked_lemon in choices else 0
    return dataclasses.replace(where, picked_lemon=choices[(at + by) % len(choices)])


def _color(where: keys.Where, blocks: abc.Sequence[Block]) -> tuple[keys.Where, str, Target | None]:
    block = next((b for b in blocks if b.digit == where.block), None)
    if block is None:
        return where, "", None
    if not block.name:
        return dataclasses.replace(_let_go(where), note="the packhouse has no color"), "", None
    return where, "", _target(where, blocks, block, None)


def _editing_step(
    where: keys.Where, key: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> tuple[keys.Where, str, Target | None]:
    if key == "escape":
        return _let_go(where), "", None
    if key.isdigit() and len(key) == 1 and not where.picked_tree:
        found, _ = keys.step(dataclasses.replace(where, editing=""), key, blocks, arrangement)
        where = dataclasses.replace(found, editing=where.editing)
        return _color(where, blocks) if where.editing == "color" else (where, "", None)

    found = _picked(where, blocks)
    letter = key.lower() if len(key) == 1 and key.isalpha() else ""
    if found:
        block, tree = found
        if (letter and letter == arrangement.trees[(block.name, tree.key)].letter) or key in (
            "down",
            "right",
            "tab",
        ):
            return _turn(where, tree, 1), "", None
        if key in ("up", "left", "shift+tab"):
            return _turn(where, tree, -1), "", None
        if key == "enter":
            return where, "", _target(where, blocks, block, tree)
    if letter and where.editing != "color":
        return _choose_tree(where, letter, blocks, arrangement), "", None
    return where, "", None


def step(
    where: keys.Where, key: str, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> tuple[keys.Where, str, Target | None]:
    """`keys.step`, with editing on top; also the edit Enter asked for, if it did."""
    where = dataclasses.replace(where, note="")
    if key == "alt+m" and where.search is None:
        return (
            dataclasses.replace(
                where, note="drag a block, its edge or a tree with the mouse to move it"
            ),
            "",
            None,
        )
    if key in ACTIONS and where.search is None:
        where = dataclasses.replace(_let_go(where), editing=ACTIONS[key])
        return _color(where, blocks) if where.editing == "color" else (where, "", None)
    if where.editing:
        return _editing_step(where, key, blocks, arrangement)
    return (*keys.step(where, key, blocks, arrangement), None)


def prompt(where: keys.Where, blocks: abc.Sequence[Block], letter: str) -> str:
    """The prompt line while editing, or "" when not."""
    if not where.editing:
        return ""

    verb = _VERBS[where.editing]
    found = _picked(where, blocks)
    if found is None:
        first = (
            (
                "a block number"
                if where.editing == "color"
                else "a block number, then a tree's letter"
            )
            if not where.block
            else "a tree's letter"
        )
        return f"{verb}: type {first} · esc cancels"

    _, tree = found
    lemon = _lemon(tree, where.picked_lemon)
    what = (
        f"lemon {lemon.brief_id or lemon.name}"
        if lemon
        else f"tmux session {tree.key}"
        if where.editing == "rename"
        else f"all {len(tree.lemons)} lemons on {tree.key}"
    )
    choices = _choices(where.editing, tree)
    more = f" · {letter} or ↑↓ for the next of {len(choices)}" if len(choices) > 1 else ""
    return f"{verb} {what}?{more} · enter {verb.split()[0]}s · esc cancels"
