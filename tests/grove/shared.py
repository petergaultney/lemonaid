"""Builders for grove models."""

from lemonaid.grove.layout import terrain
from lemonaid.grove.model import WORLD_WIDTH, Block, Lemon, Tree

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
        provider="anthropic",
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


# A stream straight across the world along row 30, and no roads.
STREAM = [[0, 30], [WORLD_WIDTH, 30]]


def plot_data(x: int, y: int, w: int, h: int, **more: object) -> dict[str, object]:
    return {"x": x, "y": y, "w": w, "h": h, "roundness": 4.5, "seed": 3, "texture": "rows", **more}


def stream_saved(plots: dict, trees: dict | None = None) -> dict:
    return {"plots": plots, "trees": trees or {}, "roads": [], "stream": STREAM}


def stream_ground() -> terrain.Covered:
    return terrain.covered((), tuple((x, y) for x, y in STREAM))
