"""Builders for grove models."""

from lemonaid.grove.model import Block, Lemon, Tree

NOW = 1_800_000_000.0
DAY = 86400.0


def lemon(
    channel: str, brief_id: str = "", status: str = "", born: float = NOW - 10 * DAY
) -> Lemon:
    return Lemon(
        channel=channel,
        notification_id=1,
        name=f"lemon {channel}",
        brief_id=brief_id,
        status=status,
        working=False,
        quiet=False,
        model="Opus 5.5",
        context="",
        emoji="",
        pinned=False,
        born=born,
        session="",
        window="",
        hidden=False,
    )


def tree(key: str, *lemons: Lemon, lead: bool = False) -> Tree:
    return Tree(key, key, lemons or (lemon(f"claude:{key}"),), lead)


def block(name: str, digit: str, *trees: Tree) -> Block:
    return Block(name, digit, "#6495ed", trees)
