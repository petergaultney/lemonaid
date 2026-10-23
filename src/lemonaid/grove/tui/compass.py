"""Moving the grove view: an arrow nudges it a few cells, Shift and an arrow a whole screen,
and Shift and a digit jumps to one of the nine screen-sized tiles around the packhouse,
clockwise from north (on a US keyboard the characters `)!@#$%^&*`); Alt and a digit does the
same on any keyboard. 0, or Home, is the middle tile, centered on the packhouse.
"""

import dataclasses

from ..draw import scene_parts
from ..layout import landmarks
from . import keys
from .frame import Grove

_TILES = {  # (across, down) from the middle tile, clockwise from north
    "0": (0, 0),
    "1": (0, -1),
    "2": (1, -1),
    "3": (1, 0),
    "4": (1, 1),
    "5": (0, 1),
    "6": (-1, 1),
    "7": (-1, 0),
    "8": (-1, -1),
}
_SHIFTED = dict(zip(")!@#$%^&*", "012345678", strict=True))
_SCREENS = {"shift+left": (-1, 0), "shift+right": (1, 0), "shift+up": (0, -1), "shift+down": (0, 1)}
_NUDGES = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}


def _tile(key: str) -> str:
    if key == "home":
        return "0"
    if key.startswith("alt+") and key[4:] in _TILES:
        return key[4:]

    return _SHIFTED.get(key, "")


def handles(where: keys.Where, key: str) -> bool:
    """Whether *key* moves the view: only over the whole grove, not in a block or a search."""
    if where.block or where.search is not None or where.picked_tree:
        return False

    return key in _SCREENS or key in _NUDGES or bool(_tile(key))


def _middle(grove: Grove) -> tuple[float, float]:
    house = grove.arrangement.plots.get(landmarks.PACKHOUSE)
    if house:
        return house.x + house.w / 2, house.y + house.h / 2

    right, bottom = scene_parts.extent(grove.arrangement)
    return right / 2, bottom / 2


def step(
    grove: Grove,
    where: keys.Where,
    key: str,
    size: tuple[int, int],
    nudge: tuple[int, int] = (2, 1),
) -> keys.Where:
    """*where* with the view moved by *key*, on a screen of *size*; an arrow moves it *nudge*
    cells, across and down.
    """
    width, height = size
    view = scene_parts.grove_view(size, grove.arrangement, where.pan)
    across, down = width / view.sx, (height - 2) / view.sy  # a screen, in grove units
    if key in _NUDGES:
        dx, dy = _NUDGES[key]
        pan = (view.left + dx * nudge[0] / view.sx, view.top + dy * nudge[1] / view.sy)
    elif key in _SCREENS:
        dx, dy = _SCREENS[key]
        pan = (view.left + dx * across, view.top + dy * down)
    else:
        (dx, dy), (cx, cy) = _TILES[_tile(key)], _middle(grove)
        pan = (cx - across / 2 + dx * across, cy - down / 2 + dy * down)
    return dataclasses.replace(where, pan=(max(0.0, pan[0]), max(0.0, pan[1])))
