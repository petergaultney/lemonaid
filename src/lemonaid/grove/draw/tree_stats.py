"""A tree's tag in the grove view while the flip key is held, short so that crowded tags keep it
whole: how many of its lemons are mid-turn, as `1/3`, its fullest context, and how long since its
latest lemon reported.
"""

import dataclasses
import re

from ..model import Tree
from . import colors
from .canvas import Canvas, put


def line(tree: Tree) -> str:
    working = sum(lemon.working for lemon in tree.lemons)
    contexts = [int(lemon.context[:-1]) for lemon in tree.lemons if lemon.context[:-1].isdigit()]
    latest = max(tree.lemons, key=lambda lemon: lemon.updated)
    return " · ".join(
        [
            f"{working}/{len(tree.lemons)}",
            *([f"{max(contexts)}%"] if contexts else []),
            *([latest.age.removesuffix(" ago")] if latest.age else []),
        ]
    )


def tagged(tree: Tree) -> Tree:
    """*tree* labeled with its stats, and without the emoji and pin its tag would otherwise mark."""
    return dataclasses.replace(
        tree,
        label=line(tree),
        lemons=tuple(dataclasses.replace(m, emoji="", pinned=False) for m in tree.lemons),
    )


def color_context(canvas: Canvas, line: str, x: int, y: int) -> None:
    """Recolor the context reading in a tag's *line*, drawn at (*x*, *y*), as the inbox colors it."""
    found = re.search(r"\b\d+%", line)
    if not found:
        return

    for i, char in enumerate(found.group(), start=found.start()):
        put(canvas, x + i, y, char, colors.reading_color(found.group()), None, bold=True)
