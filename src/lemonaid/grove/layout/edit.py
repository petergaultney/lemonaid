"""Changes to a saved layout that a person or a lemon asks for: move, resize, clear open ground
or a stump.

Each returns a new layout and leaves its input alone. A tree's spot is relative to its plot,
so trees move with their block; a block made smaller pushes the trees its edges cut off
back onto it, and a tree too big for it stands afresh inside, squeezed in.
"""

import copy
from typing import Any

from . import arrange, lead_spot


class EditError(ValueError):
    pass


def _plot(saved: dict[str, Any], group: str) -> dict[str, Any]:
    try:
        return saved["plots"][group]
    except KeyError:
        raise EditError(
            f"No plot for group {group!r}; `lemonaid grove show` lays out live groups"
        ) from None


def _pushed(spot: dict[str, Any], w: int, h: int) -> dict[str, Any] | None:
    """*spot* moved the least that puts it on a *w* by *h* plot, crown aside, or None if it
    can't fit there.
    """
    if "w" not in spot:
        return {**spot, "x": min(max(spot["x"], 0), w), "y": min(max(spot["y"], 0), h)}
    if spot["w"] > w or spot["h"] - spot["top"] > h:
        return None

    half = spot["w"] // 2
    x = min(max(spot["x"], half), w - spot["w"] + half)
    y = min(max(spot["y"], 0), h - spot["h"] + spot["top"])
    return {**spot, "x": x, "y": y}


def _push_back_cut_off(changed: dict[str, Any], group: str) -> dict[str, Any]:
    plot, spots = _plot(changed, group), changed["trees"].get(group, {})
    for key in arrange.cut_off(plot, spots):
        if not spots[key].get("gone_since"):
            pushed = _pushed(spots[key], plot["w"], plot["h"])
            spots[key] = pushed or {"letter": spots[key].get("letter", ""), "squeeze": True}
    return changed


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
    return _push_back_cut_off(changed, group)


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
    return _push_back_cut_off(changed, group)


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


def _stump(saved: dict[str, Any], group: str, key: str) -> dict[str, Any]:
    spot = saved["trees"].get(group, {}).get(key)
    if spot is None or not spot.get("gone_since"):
        raise EditError(f"No bare tree {key!r} in {group or 'no group'}")
    return spot


def place_stump(saved: dict[str, Any], group: str, key: str, x: int, y: int) -> dict[str, Any]:
    """Stand the bare tree left by tree *key* at (*x*, *y*) in its plot."""
    changed = copy.deepcopy(saved)
    _stump(changed, group, key).update(x=x, y=y)
    return changed


def clear_stump(saved: dict[str, Any], group: str, key: str) -> dict[str, Any]:
    """The layout without the bare tree left by tree *key*: its spot, and the letter it kept,
    are forgotten, as they are 30 days after the tree goes.
    """
    changed = copy.deepcopy(saved)
    _stump(changed, group, key)
    del changed["trees"][group][key]
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
