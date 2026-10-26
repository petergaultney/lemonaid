"""Moving a tree chosen whole in select mode with the arrow keys, a grove unit a press and five
with Shift. A step onto ground the tree can't stand on hops past it to the next spot that can
take it; with none that way, the tree stays where it was.
"""

import dataclasses

from . import drop, garden
from .frame import Grove

_ARROWS = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}
_FAR = 5
_HOPS = 20  # grove units a step looks past a refused spot for one that takes the tree


def step(key: str) -> tuple[int, int] | None:
    """How far *key* moves a tree, across and down, or None when it isn't an arrow."""
    far = key.startswith("shift+")
    found = _ARROWS.get(key.removeprefix("shift+"))
    if found is None:
        return None

    return found[0] * (_FAR if far else 1), found[1] * (_FAR if far else 1)


def start(grove: Grove, digit: str, tree_key: str) -> garden.Drag | str:
    """A drag of the tree that hasn't moved yet, or why the tree can't move."""
    block = next(b for b in grove.blocks if b.digit == digit)
    if grove.arrangement.plots[block.name].texture == "house":
        return "the packhouse's bays stay in order"

    letter = grove.arrangement.trees[(block.name, tree_key)].letter
    return garden.Drag(block, tree_key, frozenset(), (0, 0), (1.0, 1.0), name=digit + letter)


def nudged(base: Grove, drag: garden.Drag, by: tuple[int, int]) -> tuple[garden.Drag, str]:
    """*drag* moved *by* more from *base*, or past that to the first spot that takes the tree;
    *drag* unmoved and why when no spot that way does.
    """
    unit = (min(1, max(-1, by[0])), min(1, max(-1, by[1])))
    problem = ""
    for extra in range(_HOPS + 1):
        moved = (
            drag.moved[0] + by[0] + unit[0] * extra,
            drag.moved[1] + by[1] + unit[1] * extra,
        )
        tried = dataclasses.replace(drag, moved=moved)
        problem = drop.refused(base, tried)
        if not problem:
            return tried, ""
        if extra == 0 and problem == "a tree stays on its block's ground":
            break  # past the edge, farther is off the ground too
    return drag, problem
