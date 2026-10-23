"""Finding ground for a new block, and a spot in a block for a new tree.

Both search a fixed, seeded set of candidates, so the same grove always lays out the same way.
"""

import math
from collections import abc

from ..draw.ground import inside, noise, word_hash
from ..model import WORLD_HEIGHT, WORLD_WIDTH, Plot

Rect = tuple[int, int, int, int]  # x, y, w, h
_TEXTURES = ("rows", "diag", "wave", "dots")


def overlaps(a: Rect, b: Rect, gap: int) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw + gap and bx < ax + aw + gap and ay < by + bh + gap and by < ay + ah + gap


def plot_size(tree_area: int) -> tuple[int, int]:
    """A plot roughly three times as wide as tall (cells are twice as tall as wide), with room to grow."""
    area = max(200, tree_area * 1.35)
    h = max(9, round(math.sqrt(area / 2.8)))
    return max(28, round(area / h)), h


def new_plot(name: str, size: tuple[int, int], taken: abc.Sequence[Rect]) -> Plot:
    """Ground for a block named *name*: the free spot nearest the grove's middle, beyond its edge if full."""
    w, h = size
    seed = word_hash(name)
    cx, cy = WORLD_WIDTH / 2, WORLD_HEIGHT / 2
    best: Rect | None = None
    best_distance = math.inf
    right = max([WORLD_WIDTH, *(x + rw for x, _, rw, _ in taken)])
    for y in range(1, max(2, WORLD_HEIGHT - h)):
        for x in range(0, right + w, 2):
            rect = (x, y, w, h)
            if any(overlaps(rect, other, 1) for other in taken):
                continue
            distance = (
                math.hypot(x + w / 2 - cx, (y + h / 2 - cy) * 2) + (x + w > WORLD_WIDTH) * 1000
            )
            if distance < best_distance:
                best, best_distance = rect, distance
    x, y, w, h = best or (right + 2, 1, w, h)
    return Plot(
        x,
        y,
        w,
        h,
        roundness=(2.4, 2.8, 3.4, 4.5)[seed % 4],
        seed=seed % 97,
        texture=_TEXTURES[seed % 4],
    )


def _fits(plot: Plot, rect: Rect, placed: abc.Sequence[Rect], loose: bool) -> bool:
    x, y, w, h = rect
    if x < 1 or y < 1 or x + w > plot.w - 1 or y + h > plot.h - 1:
        return False
    probes = (
        [(x + w / 2, y + h / 2), (x + w / 2, y + 1)]
        if loose
        else [
            (x, y),
            (x + w - 1, y),
            (x, y + h - 1),
            (x + w - 1, y + h - 1),
            (x + w / 2, y + h / 2),
        ]
    )
    if not all(inside(plot, plot.x + px, plot.y + py) for px, py in probes):
        return False
    return not any(overlaps(rect, other, 0) for other in placed)


def overlap_area(rect: Rect, placed: abc.Sequence[Rect]) -> int:
    x, y, w, h = rect
    return sum(
        max(0, min(x + w, px + pw) - max(x, px)) * max(0, min(y + h, py + ph) - max(y, py))
        for px, py, pw, ph in placed
    )


def new_spot(
    plot: Plot,
    size: tuple[int, int],
    placed: abc.Sequence[Rect],
    toward: tuple[float, float] | None = None,
) -> tuple[int, int]:
    """Where a footprint of *size* goes in *plot*, relative to its corner.

    With *toward*, a point relative to the corner, it goes as near that point as it fits;
    otherwise as far from the others as it can, with some randomness, so trees spread through
    the block without lining up. With no room left it stands past the right of every other tree,
    spilling out of the plot rather than covering one.
    """
    w, h = size
    centers = [(px + pw / 2, py + ph / 2) for px, py, pw, ph in placed]
    best: tuple[int, int] | None = None
    best_score = -math.inf
    for k in range(2400):
        x = round(noise(plot.seed * 97 + len(placed), k) * max(1, plot.w - w))
        y = round(noise(plot.seed * 89 + k, len(placed)) * max(1, plot.h - h))
        if not _fits(plot, (x, y, w, h), [], loose=True):
            continue
        if not _fits(plot, (x, y, w, h), placed, loose=k >= 1200 and best is None):
            continue
        cx, cy = x + w / 2, y + h / 2
        if toward:
            score = -math.hypot(cx - toward[0], (cy - toward[1]) * 2)
        else:
            nearest = min((math.hypot(cx - ox, (cy - oy) * 2) for ox, oy in centers), default=99.0)
            score = min(nearest, 40) + noise(k, len(placed) * 31) * 8
        if score > best_score:
            best, best_score = (x, y), score
    spill = (max([plot.w, *(px + pw for px, _, pw, _ in placed)]) + 1, max(1, (plot.h - h) // 2))
    return best or spill
