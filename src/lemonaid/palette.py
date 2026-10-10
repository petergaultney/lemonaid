"""Stable colours for names (places, groups, tmux window labels) drawn from the whole hue wheel.

Every slot has the same saturation, so none is grey, and one of `_TIERS`'s relative
luminances, so each reads against black text (group header fills) and against a dark
terminal background. Candidates come from hues `_HUE_STEP` degrees apart, and a candidate
less than `MIN_DISTANCE` (OKLab) from a slot already kept is dropped, so no two slots are
near-identical.
"""

import colorsys
import re
from collections import abc

_HUE_STEP = 10
# Relative luminance (WCAG) per tier: 7:1 to 12:1 against black.
_TIERS = (0.32, 0.42, 0.55)
_SATURATION = 0.75


def _luminance(r: float, g: float, b: float) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _slot_colour(hue: int, luminance: float) -> str:
    low, high = 0.0, 1.0
    for _ in range(24):
        mid = (low + high) / 2
        if _luminance(*colorsys.hls_to_rgb(hue / 360, mid, _SATURATION)) < luminance:
            low = mid
        else:
            high = mid
    r, g, b = colorsys.hls_to_rgb(hue / 360, (low + high) / 2, _SATURATION)

    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def _linear(channel: int) -> float:
    c = channel / 255

    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _oklab(colour: str) -> tuple[float, float, float]:
    r, g, b = (_linear(int(colour[i : i + 2], 16)) for i in (1, 3, 5))
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)

    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def distance(a: str, b: str) -> float:
    """Perceptual distance (OKLab) between two `#rrggbb` colours; about 0.02 is just noticeable."""
    return sum((x - y) ** 2 for x, y in zip(_oklab(a), _oklab(b), strict=False)) ** 0.5


MIN_DISTANCE = 0.05


def _thinned(candidates: abc.Iterable[str]) -> tuple[str, ...]:
    kept: list[str] = []
    for candidate in candidates:
        if all(distance(candidate, other) >= MIN_DISTANCE for other in kept):
            kept.append(candidate)

    return tuple(kept)


SLOTS = _thinned(
    _slot_colour(hue, luminance) for luminance in _TIERS for hue in range(0, 360, _HUE_STEP)
)


def is_colour(text: str) -> bool:
    return re.fullmatch(r"#[0-9a-fA-F]{6}", text) is not None


def djb2(s: str) -> int:
    """DJB2 hash algorithm for deterministic string hashing."""
    h = 5381
    for c in s:
        h = ((h * 33) + ord(c)) & 0xFFFFFFFF

    return h


def colour_for(name: str) -> str:
    return SLOTS[djb2(name) % len(SLOTS)]


GROUP_MIN_DISTANCE = 0.08


def assign_groups(names: abc.Iterable[str], pinned: abc.Mapping[str, str]) -> dict[str, str]:
    """A colour for each of *names*: its `pinned` one, else its hash slot moved off any look-alike.

    Names are taken in sorted order, so the result depends only on the set of
    names. A name keeps its hash slot unless that is within `GROUP_MIN_DISTANCE`
    of a colour already given out, and then takes the nearest slot that isn't;
    with none left, it keeps its hash slot.
    """
    wanted = set(names)
    given = {name: colour for name, colour in pinned.items() if name in wanted}
    for name in sorted(wanted - given.keys()):
        taken = list(given.values())
        slot = colour_for(name)
        free = [
            s for s in SLOTS if all(distance(s, other) >= GROUP_MIN_DISTANCE for other in taken)
        ]
        given[name] = (
            slot
            if slot in free or not free
            else min(free, key=lambda candidate: distance(candidate, slot))
        )

    return given
