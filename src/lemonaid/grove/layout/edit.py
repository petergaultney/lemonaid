"""Changes to a saved layout that a person or a lemon asks for: move, resize, clear open ground.

Each returns a new layout and leaves its input alone. A tree's spot is relative to its plot,
so trees move with their block; a block made smaller can leave trees outside its outline,
which the next new tree's placement avoids but drawing does not hide.
"""

import copy
from typing import Any

from . import lead_spot


class EditError(ValueError):
    pass


def _plot(saved: dict[str, Any], group: str) -> dict[str, Any]:
    try:
        return saved["plots"][group]
    except KeyError:
        raise EditError(
            f"No plot for group {group!r}; `lemonaid grove show` lays out live groups"
        ) from None


def move(saved: dict[str, Any], group: str, x: int, y: int) -> dict[str, Any]:
    if x < 0 or y < 0:
        raise EditError("A plot's corner can't be above or left of the grove")

    changed = copy.deepcopy(saved)
    _plot(changed, group).update(x=x, y=y)
    return changed


def resize(saved: dict[str, Any], group: str, w: int, h: int) -> dict[str, Any]:
    if w < 12 or h < 5:
        raise EditError("A plot needs at least 12 columns and 5 rows")

    changed = copy.deepcopy(saved)
    _plot(changed, group).update(w=w, h=h)
    return changed


def reframe(saved: dict[str, Any], group: str, x: int, y: int, w: int, h: int) -> dict[str, Any]:
    """Move and resize a block's plot at once, its trees staying where they stand on the ground."""
    if w < 12 or h < 5:
        raise EditError("A plot needs at least 12 columns and 5 rows")
    if x < 0 or y < 0:
        raise EditError("A plot's corner can't be above or left of the grove")

    changed = copy.deepcopy(saved)
    plot = _plot(changed, group)
    shift = plot["x"] - x, plot["y"] - y
    for spot in changed["trees"].get(group, {}).values():
        if "x" in spot:
            spot["x"], spot["y"] = spot["x"] + shift[0], spot["y"] + shift[1]
    plot.update(x=x, y=y, w=w, h=h)
    return changed


def place_tree(
    saved: dict[str, Any], group: str, key: str, lead: bool, x: int, y: int
) -> dict[str, Any]:
    """Stand tree *key* at (*x*, *y*) in its plot; a *lead* tree's spot is the block's lead spot."""
    changed = copy.deepcopy(saved)
    spots = changed["trees"].get(group, {})
    spot = spots.get(lead_spot.KEY) if lead and lead_spot.KEY in spots else spots.get(key)
    if spot is None:
        raise EditError(f"No spot for tree {key!r} in {group or 'no group'}")

    spot.update(x=x, y=y)
    return changed


def reshape(saved: dict[str, Any], group: str, roundness: float) -> dict[str, Any]:
    if not 1.5 <= roundness <= 12:
        raise EditError(
            "Roundness runs from 1.5 (pointed) through 2 (an ellipse) to 12 (nearly square)"
        )

    changed = copy.deepcopy(saved)
    _plot(changed, group)["roundness"] = roundness
    return changed


def clear_open(saved: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The layout without its open ground, and the names of the groups that held it."""
    changed = copy.deepcopy(saved)
    cleared = [
        name for name, plot in changed["plots"].items() if plot.get("open_since") is not None
    ]
    for name in cleared:
        del changed["plots"][name]
        changed["trees"].pop(name, None)
    return changed, cleared


def share_tree(saved: dict[str, Any], group: str, old: str, new: str) -> dict[str, Any]:
    """The layout with tree *old*'s spot and letter under key *new* too, for while a rename is
    under way: whichever key a reload sees, the tree stands in its own spot.
    """
    changed = copy.deepcopy(saved)
    spots = changed["trees"].get(group, {})
    if old in spots:
        spots[new] = copy.deepcopy(spots[old])
    return changed


def rename_tree(saved: dict[str, Any], group: str, old: str, new: str) -> dict[str, Any]:
    """The layout with tree *old*'s spot and letter kept under its new key *new*."""
    changed = share_tree(saved, group, old, new)
    changed["trees"].get(group, {}).pop(old, None)
    return changed
