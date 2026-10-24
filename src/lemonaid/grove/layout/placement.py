"""Finding ground for a new block, and a spot in a block for a new tree.

Both search a fixed, seeded set of candidates, so the same grove always lays out the same way.
"""

import math
from collections import abc

from ..draw.ground import inside, noise, word_hash
from ..model import WORLD_HEIGHT, WORLD_WIDTH, Plot

Rect = tuple[int, int, int, int]  # x, y, w, h
# A footprint's width and height, and how far it may reach above its plot's top edge: a tree's
# crown may rise past the top of its block, so long as its middle, trunk and tag are on it.
Size = tuple[int, int, int]
_GAP = 1  # grove units kept clear between a new tree, tag included, and every other
_TEXTURES = ("rows", "diag", "wave", "dots")


def overlaps(a: Rect, b: Rect, gap: int) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw + gap and bx < ax + aw + gap and ay < by + bh + gap and by < ay + ah + gap


def plot_size(tree_area: int, largest: tuple[int, int]) -> tuple[int, int]:
    """A plot roughly three times as wide as tall (cells are twice as tall as wide), with room to
    grow, and room in its rounded middle for its *largest* tree, (w, h) with its tag.
    """
    area = max(200, tree_area * 1.35)
    h = max(9, largest[1] + 4, round(math.sqrt(area / 2.8)))
    return max(28, largest[0] + 6, round(area / h)), h


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


def _fits(plot: Plot, rect: Rect, placed: abc.Sequence[Rect], above: int = 0) -> bool:
    """Whether *rect* lies inside *plot*'s ground, but for its top *above* units, clear of every
    one of *placed*.
    """
    x, y, w, h = rect
    if x < 1 or y + above < 1 or x + w > plot.w - 1 or y + h > plot.h - 1:
        return False
    probes = [
        (x, y + above),
        (x + w - 1, y + above),
        (x, y + h - 1),
        (x + w - 1, y + h - 1),
        (x + w / 2, y + h / 2),
    ]
    if not all(inside(plot, plot.x + px, plot.y + py) for px, py in probes):
        return False
    return not any(overlaps(rect, other, _GAP) for other in placed)


def overlap_area(rect: Rect, placed: abc.Sequence[Rect]) -> int:
    x, y, w, h = rect
    return sum(
        max(0, min(x + w, px + pw) - max(x, px)) * max(0, min(y + h, py + ph) - max(y, py))
        for px, py, pw, ph in placed
    )


def _spill(plot: Plot, size: tuple[int, int], placed: abc.Sequence[Rect]) -> tuple[int, int]:
    w, h = size
    clear = (
        (x, y)
        for y in range(-h, plot.h + 1)
        for x in range(-w, plot.w + w * (len(placed) + 1))
        if not any(overlaps((x, y, w, h), other, 0) for other in placed)
    )
    return min(
        clear,
        key=lambda xy: math.hypot(xy[0] + w / 2 - plot.w / 2, (xy[1] + h / 2 - plot.h / 2) * 2),
    )


def _squeeze(plot: Plot, size: Size, placed: abc.Sequence[Rect]) -> tuple[int, int]:
    """Where a footprint of *size* covers the least of *placed* with its middle on *plot*'s
    ground, nearest the middle among equals: for a tree with no room left in a full block. One
    longer than the plot, which only a plot boxed in by other blocks keeps, stands with its
    crown's middle on the plot's top edge and overhangs the bottom.
    """
    w, full, above = size
    h = full - above  # the part that must be on the plot
    xs = range(0, plot.w - w + 1) if w <= plot.w else [(plot.w - w) // 2]
    ys = [y - above for y in (range(0, plot.h - h + 1) if h <= plot.h else [0])]
    middle = ((plot.w - w) // 2, max(0, (plot.h - h) // 2) - above)
    on_ground = [
        (x, y)
        for y in ys
        for x in xs
        if inside(plot, plot.x + x + w / 2, plot.y + y + above + h / 2)
    ] or [middle]
    return min(
        on_ground,
        key=lambda xy: (
            overlap_area((xy[0], xy[1], w, full), placed),
            math.hypot(xy[0] + w / 2 - plot.w / 2, (xy[1] + above + h / 2 - plot.h / 2) * 2),
        ),
    )


def room_for(
    plot: Plot,
    size: Size,
    placed: abc.Sequence[Rect],
    toward: tuple[float, float] | None = None,
) -> tuple[int, int] | None:
    """Where a footprint of *size* goes in *plot*, relative to its corner, or None if it fits
    nowhere.

    It fits inside the plot, tag and all but for the top it may raise above it, a grove unit
    clear of the others. With
    *toward*, a point relative to the corner, it goes as near that point as it fits;
    otherwise as far from the others as it can, with some randomness, so trees spread through
    the block without lining up.
    """
    w, h, above = size
    centers = [(px + pw / 2, py + ph / 2) for px, py, pw, ph in placed]
    best: tuple[int, int] | None = None
    best_score = -math.inf
    candidates = (
        [(x, y) for y in range(1 - above, plot.h - h) for x in range(1, plot.w - w)]
        if toward
        else [
            (
                round(noise(plot.seed * 97 + len(placed), k) * max(1, plot.w - w)),
                round(noise(plot.seed * 89 + k, len(placed)) * max(1, plot.h - h + above)) - above,
            )
            for k in range(2400)
        ]
    )
    for k, (x, y) in enumerate(candidates):
        if not _fits(plot, (x, y, w, h), placed, above):
            continue
        cx, cy = x + w / 2, y + h / 2
        if toward:
            score = -math.hypot(cx - toward[0], (cy - toward[1]) * 2)
        else:
            nearest = min((math.hypot(cx - ox, (cy - oy) * 2) for ox, oy in centers), default=99.0)
            score = min(nearest, 40) + noise(k, len(placed) * 31) * 8
        if score > best_score:
            best, best_score = (x, y), score
    return best


def first_room(
    plot: Plot,
    sizes: abc.Sequence[Size],
    placed: abc.Sequence[Rect],
    toward: tuple[float, float] | None = None,
) -> tuple[tuple[int, int], Size] | None:
    """Where a footprint goes in *plot*, and the size of it that fits: the first of *sizes*,
    largest first, that `room_for` finds room for; None if none fits.
    """
    for size in sizes:
        spot = room_for(plot, size, placed, toward)
        if spot is not None:
            return spot, size
    return None


def new_spot(
    plot: Plot,
    sizes: abc.Sequence[Size],
    placed: abc.Sequence[Rect],
    toward: tuple[float, float] | None = None,
    squeeze: bool = False,
) -> tuple[tuple[int, int], Size]:
    """As `first_room`, but with no room for any size the smallest spills just past the plot's
    edge, as near its middle as it stands clear of every other tree, for the plot to grow into;
    or, with *squeeze*, for a plot that can't, goes where it covers the least of the others,
    still on the plot's ground.
    """
    return first_room(plot, sizes, placed, toward) or (
        _squeeze(plot, sizes[-1], placed) if squeeze else _spill(plot, sizes[-1][:2], placed),
        sizes[-1],
    )
