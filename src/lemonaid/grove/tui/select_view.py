"""How select mode shows its choice: the prompt line, the chosen row, and whose card to draw."""

from collections import abc

from ..draw import lemon_list, scene_parts
from ..layout.arrange import Arrangement
from ..model import Block, Lemon, Tree
from . import choice, keys

_EDITS = "r s a p g c edit"


def key_name(key: str) -> str:
    """A key as the help writes it: `Tab`, `F6`, or a character as it is."""
    return key.capitalize() if len(key) > 1 else key


def prompt(
    where: keys.Where, blocks: abc.Sequence[Block], arrangement: Arrangement, select_key: str
) -> str:
    """The prompt line in select mode, or "" outside it."""
    if not where.selecting or where.search is not None or where.editing:
        return ""

    leave = f"esc or {key_name(select_key)} leaves select mode"
    block = next((b for b in blocks if b.digit == where.block), None)
    if block is None:
        return f"select: type a block number, or / to search · {leave}"

    at = f"select {choice.typed(where, blocks, arrangement)}"
    if where.dot or where.whole:
        return f"{at}: type the tree's letter · {leave}"
    if where.tree:
        return f"{at}: type the lemon's place on the tree, 1 to 9, or 0 and a letter past 9"

    found = choice.chosen(where, blocks, arrangement)
    if found is None:
        return (
            f"{at} · {block.name or 'no group'}: a letter chooses a tree's first lemon, $ and a"
            f" letter the whole tree · {leave}"
        )

    _, tree, lemon = found
    if lemon is None:
        return f"{at} · {tree.key}: arrows move it · {_EDITS}"
    return f"{at} · {lemon.brief_id or lemon.name}: {_EDITS} · ↑↓ along the tree · enter jumps"


def carded(
    where: keys.Where, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> tuple[Tree, Lemon] | None:
    """The chosen tree and the lemon whose card shows: the chosen one, else the tree's first."""
    found = choice.chosen(where, blocks, arrangement) if where.selecting else None
    if found is None:
        return None

    _, tree, lemon = found
    return tree, lemon or tree.lemons[0]


def highlight(
    where: keys.Where, blocks: abc.Sequence[Block], arrangement: Arrangement
) -> scene_parts.Highlight | None:
    """The chosen row, or the chosen tree's title, marked as an edit's target is; nothing fades."""
    found = choice.chosen(where, blocks, arrangement) if where.selecting else None
    if found is None:
        return None

    block, tree, lemon = found
    return scene_parts.Highlight(
        frozenset(scene_parts.block_channels(block)),
        (lemon or tree.lemons[0]).channel,
        lemon.channel if lemon else lemon_list.session(tree),
    )


def card_title(
    where: keys.Where, blocks: abc.Sequence[Block], arrangement: Arrangement, lemon: Lemon
) -> str:
    """The choice's keys, then where its lemon runs, as `5.s1 · core:3`."""
    runs = ":".join(part for part in (lemon.session, lemon.window) if part)
    return " · ".join(part for part in (choice.typed(where, blocks, arrangement), runs) if part)
