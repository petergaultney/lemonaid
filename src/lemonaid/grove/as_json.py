"""The grove as plain data: what `grove show --json` prints and the grove window draws."""

import dataclasses
from collections import abc
from typing import Any

from .layout import arrange
from .model import Block


def grove(found: abc.Iterable[Block], arrangement: arrange.Arrangement) -> dict[str, Any]:
    return {
        "blocks": [
            {
                "digit": block.digit,
                "group": block.name,
                "home": block.home,
                "color": block.color,
                "plot": dataclasses.asdict(arrangement.plots[block.name]),
                "trees": [
                    {
                        "key": tree.key,
                        "letter": standing.letter,
                        "label": standing.label,
                        "lead": tree.lead,
                        "spot": [standing.cx, standing.cy],
                        "size": standing.size,
                        "bay": standing.bay,
                        "lemons": [dataclasses.asdict(lemon) for lemon in tree.lemons],
                    }
                    for tree in block.trees
                    for standing in (arrangement.trees[(block.name, tree.key)],)
                ],
                "stumps": [
                    {"key": stump.key, "label": stump.label, "spot": [stump.cx, stump.cy]}
                    for stump in arrangement.stumps.get(block.name, ())
                ],
            }
            for block in found
        ],
        "open": [dataclasses.asdict(plot) for plot in arrangement.open],
        "roads": [list(map(list, road)) for road in arrangement.roads],
        "stream": list(map(list, arrangement.stream)),
        "error": None,
    }
