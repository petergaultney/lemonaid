"""Applying a proposed layout, a copy of the saved layout that a lemon rearranged, to the saved one.

Block plots and tree spots apply. A tree's spot is relative to its plot, so a tree the proposal
doesn't move moves with its block. The proposal's roads and stream are left out.
"""

import copy
import itertools
from collections import abc
from typing import Any, NamedTuple

from ..draw import ground
from ..model import Block, Plot
from . import edit, tangles

_PLACED = ("x", "y", "w", "h", "roundness")


class Applied(NamedTuple):
    layout: dict[str, Any]
    applied: list[str]
    skipped: list[str]  # in the proposal only: the group ended and its ground was cleared since
    kept: list[str]  # in the saved layout only: new since the proposal, so left where it is


def _name(group: str) -> str:
    return group or "the ungrouped block"


def _plot(data: dict[str, Any]) -> Plot:
    return Plot(
        data["x"], data["y"], data["w"], data["h"], data["roundness"], data["seed"], data["texture"]
    )


def _check_plot(group: str, data: object) -> None:
    if not isinstance(data, dict) or any(
        isinstance(data.get(key), bool) or not isinstance(data.get(key), int)
        for key in ("x", "y", "w", "h")
    ):
        raise edit.EditError(f"{_name(group)}: x, y, w and h must be whole numbers")
    roundness = data.get("roundness")
    if isinstance(roundness, bool) or not isinstance(roundness, int | float):
        raise edit.EditError(f"{_name(group)}: roundness must be a number")
    if not 1.5 <= roundness <= 12:  # NaN fails this too
        raise edit.EditError(f"{_name(group)}: roundness runs from 1.5 to 12")
    if data["w"] < 12 or data["h"] < 5:
        raise edit.EditError(f"{_name(group)}: a plot needs at least 12 columns and 5 rows")
    if data["x"] < 0 or data["y"] < 0:
        raise edit.EditError(f"{_name(group)}: a plot's corner can't be above or left of the grove")


def _check_apart(layout: dict[str, Any]) -> None:
    blocks = [(name, d) for name, d in layout["plots"].items() if d.get("open_since") is None]
    for (a, plot_a), (b, plot_b) in itertools.combinations(blocks, 2):
        if ground.shared(_plot(plot_a), _plot(plot_b)):
            raise edit.EditError(f"{_name(a)} and {_name(b)} would be on each other's ground")


def _replant(changed: dict[str, Any], proposed: dict[str, Any], group: str) -> None:
    """Stand each tree in *group* that both layouts have, live in both, where *proposed* has it."""
    spots, wanted = changed["trees"].get(group, {}), proposed.get("trees", {}).get(group, {})
    for key, spot in wanted.items() if isinstance(wanted, dict) else ():
        live = spots.get(key)
        if not isinstance(spot, dict) or live is None or live.get("gone_since"):
            continue
        if spot.get("gone_since") or "x" not in spot:
            continue

        if any(isinstance(spot.get(c), bool) or not isinstance(spot.get(c), int) for c in "xy"):
            raise edit.EditError(f"{_name(group)}: tree {key!r} needs whole-number x and y")
        live.update(x=spot["x"], y=spot["y"])


def apply(saved: dict[str, Any], proposed: dict[str, Any], blocks: abc.Iterable[Block]) -> Applied:
    """*saved*, laid out for *blocks*, with each plot and tree spot it shares with *proposed*
    placed as *proposed* has it. Raises EditError, naming the block or tree, if a block would
    cross a road or the stream or another block, or a tree would reach past its block or stand
    on another tree.
    """
    changed = copy.deepcopy(saved)
    common = [name for name in proposed["plots"] if name in changed["plots"]]
    for name in common:
        _check_plot(name, proposed["plots"][name])
        changed["plots"][name].update({key: proposed["plots"][name][key] for key in _PLACED})

    # Blocks first: one may take over open ground that was moved too.
    for name in sorted(
        common, key=lambda name: changed["plots"][name].get("open_since") is not None
    ):
        if name not in changed["plots"]:
            continue

        try:
            edit.settle(changed, name)
        except edit.EditError as error:
            raise edit.EditError(f"{_name(name)}: {error}") from None
        edit.push_back_cut_off(changed, name)
    for name in common:
        if changed["plots"].get(name, {}).get("open_since", True) is None:
            _replant(changed, proposed, name)
    _check_apart(changed)
    tangles.check(blocks, saved, changed, common)
    return Applied(
        changed,
        [name for name in common if name in changed["plots"]],
        [name for name in proposed["plots"] if name not in saved["plots"]],
        [name for name in saved["plots"] if name not in proposed["plots"]],
    )
