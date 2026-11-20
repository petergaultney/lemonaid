"""Whether the grove window counts as over the terminal: covering at least a share of the
terminal's front window (`[tui] grove_window_cover_share`). Over it, the window covers the terminal
on each summon and hides after a jump; elsewhere it floats, kept where it was left, and stays up.

Frames are (x, y, w, h) in one coordinate system, as AppKit has them.
"""

from collections import abc

Frame = abc.Sequence[float]


def covered_share(grove: Frame, terminal: Frame) -> float:
    """How much of *terminal*'s area *grove* covers, from 0 to 1."""
    gx, gy, gw, gh = grove
    tx, ty, tw, th = terminal
    across = max(0.0, min(gx + gw, tx + tw) - max(gx, tx))
    down = max(0.0, min(gy + gh, ty + th) - max(gy, ty))
    return across * down / (tw * th) if tw > 0 and th > 0 else 0.0


def over_terminal(grove: Frame, terminal: Frame | None, share: float) -> bool:
    """With no terminal window to measure against, the window counts as over it, as it would
    cover the screen in its place."""
    return terminal is None or covered_share(grove, terminal) >= share
