"""What an edit chosen in select mode acts on, and the prompt line while it asks what it needs."""

import dataclasses
from collections import abc

from ..model import Block, Lemon, Tree
from . import keys

_VERBS = {
    "rename": "renaming",
    "snooze": "snoozing",
    "archive": "archiving",
    "pin": "pinning or unpinning",
    "group": "moving to another group",
    "color": "recoloring",
}


@dataclasses.dataclass(frozen=True)
class Target:
    action: str  # one of `selecting.VERBS`' values
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


def edit_choices(action: str, tree: Tree) -> list[str]:
    """What *action* can act on, in turn: the whole tree, "", where it can, then each lemon."""
    whole = renames_session(tree) if action == "rename" else len(tree.lemons) > 1
    return [*([""] if whole else []), *(lemon.channel for lemon in tree.lemons)]


def target(
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


def prompt(where: keys.Where, blocks: abc.Sequence[Block]) -> str:
    """What an edit under way is changing, or "" when none is."""
    if not where.editing:
        return ""

    verb = _VERBS[where.editing]
    found = _picked(where, blocks)
    if found is None:
        block = next((b for b in blocks if b.digit == where.block), None)
        return f"{verb} block {block.name if block else where.block}"

    _, tree = found
    lemon = _lemon(tree, where.picked_lemon)
    if lemon:
        return f"{verb} lemon {lemon.brief_id or lemon.name}"
    if where.editing == "rename":
        return f"{verb} tmux session {tree.key}"
    return f"{verb} all {len(tree.lemons)} lemons on {tree.key}"
