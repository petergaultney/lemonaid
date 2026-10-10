"""Stable colours for names (places, groups, tmux window labels) drawn from the whole hue wheel.

Every slot has the same saturation, so none is grey, and one of `_TIERS`'s relative
luminances, so each reads against black text (group header fills) and against a dark
terminal background. Hues are `_HUE_STEP` degrees apart.
"""

import colorsys

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


SLOTS = tuple(
    _slot_colour(hue, luminance) for luminance in _TIERS for hue in range(0, 360, _HUE_STEP)
)


def djb2(s: str) -> int:
    """DJB2 hash algorithm for deterministic string hashing."""
    h = 5381
    for c in s:
        h = ((h * 33) + ord(c)) & 0xFFFFFFFF

    return h


def colour_for(name: str) -> str:
    return SLOTS[djb2(name) % len(SLOTS)]
