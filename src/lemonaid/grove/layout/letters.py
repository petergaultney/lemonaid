"""Giving each live tree in a block a letter of its own."""

from collections import abc
from typing import Any

from ..model import Tree
from . import labels


def _live_letters(spots: dict[str, Any], live: set[str], spot: dict[str, Any]) -> set[str]:
    return {s["letter"] for key, s in spots.items() if key in live and s is not spot}


def settle(trees: abc.Sequence[Tree], spots: dict[str, Any], short: abc.Mapping[str, str]) -> None:
    """Give each live tree a letter no other live tree holds; a lead's own letter is
    `LEAD_LETTER`, so its spot holds none. A tree past the supply stays keyless until one frees.
    """
    live = {tree.key for tree in trees}
    for tree in trees:
        if tree.lead:
            spots[tree.key]["letter"] = ""

    held: set[str] = set()
    for tree in trees:
        if tree.lead:
            continue

        spot = spots[tree.key]

        letter = spot["letter"]
        if (
            not letter
            or letter not in labels.LETTERS
            or letter in held
            or letter == labels.LEAD_LETTER
        ):
            letter = labels.pick_letter(short[tree.key], held | _live_letters(spots, live, spot))
            spot["letter"] = letter
            for other in spots.values():
                if letter and other is not spot and other["letter"] == letter:
                    other["letter"] = ""  # a gone tree's

        if letter:
            held.add(letter)
