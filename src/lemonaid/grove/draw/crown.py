"""A crown's leaves as pixels, four to a cell, each shaded as part of a clump lit from the upper
left, with its trunk showing between the clumps, then packed into quadrant characters of at
most two colors a cell.
"""

import functools
from collections import abc

from . import clumps
from .canvas import QUADRANTS

# A pixel's paint: a leaf shade, 0 darkest to 3 lightest; bark lit or shaded; or none.
BARK, BARK_SHADE, NONE = 4, 5, -1
_QUARTERS = ((0.25, 0.25, 1), (0.75, 0.25, 2), (0.25, 0.75, 4), (0.75, 0.75, 8))


def _front(
    blobs: abc.Sequence[clumps.Blob], dx: float, dy: float
) -> tuple[float, float, float] | None:
    """Where (*dx*, *dy*) falls on the frontmost blob that covers it, as fractions of its radii,
    and that blob's light.
    """
    for bx, by, brx, bry, lit in reversed(blobs):
        u, v = (dx - bx) / brx, (dy - by) / bry
        if u * u + v * v <= 1:
            return u, v, lit

    return None


def _leaf(u: float, v: float, lit: float, low: float) -> int:
    """The shade at (*u*, *v*) on a clump that gets *lit* of the light, *low* of the way down the
    crown: a lit cap toward the light, a shaded crescent away from it, darkest underneath.
    """
    if (u + 0.3) ** 2 + (v + 0.42) ** 2 < 0.22 * lit - 0.03:
        return 3

    if (u + 0.1) ** 2 + (v + 0.25) ** 2 < 0.5 + 0.35 * lit:
        return 2

    return 0 if low > 0.8 else 1


def _paint(
    blobs: abc.Sequence[clumps.Blob],
    dx: float,
    dy: float,
    depth: tuple[float, float],
    trunk: float,
    bark: int,
) -> int:
    """A pixel's paint; *depth* is the crown's top and bottom, and *trunk* the trunk's middle,
    all relative to the crown's center, and *bark* its width in half cells. Between the clumps
    the trunk shows, forking upward.
    """
    on = _front(blobs, dx, dy)
    if on:
        return _leaf(*on, (dy - depth[0]) / (depth[1] - depth[0]))

    spread = bark / 4 + max(0.0, depth[1] - 0.8 - dy) * 0.9
    if not 0 <= dy <= depth[1] or abs(dx - trunk) > spread:
        return NONE

    return BARK if dx < trunk else BARK_SHADE


def _apart(a: int, b: int) -> int:
    if a < BARK and b < BARK:
        return abs(a - b)

    return 0 if a == b else 1 if a >= BARK and b >= BARK else 4


def _pack(paints: abc.Sequence[int]) -> tuple[int, int, int]:
    """A cell's four pixel paints as (quadrant bits, paint drawn, paint behind or NONE)."""
    present = [paint for paint in paints if paint != NONE]
    if len(present) < 4:
        # At the crown's edge: one paint, the most common, the darker leaf on a tie.
        paint = max(sorted(set(present)), key=present.count)
        return (
            sum(bit for p, (_, _, bit) in zip(paints, _QUARTERS, strict=True) if p != NONE),
            paint,
            NONE,
        )

    distinct = sorted(set(present))
    back, drawn = min(
        ((a, b) for a in distinct for b in distinct if a <= b),
        key=lambda pair: (sum(min(_apart(p, pair[0]), _apart(p, pair[1])) for p in present), pair),
    )
    if back == drawn:
        return 15, drawn, back

    bits = sum(
        bit
        for p, (_, _, bit) in zip(paints, _QUARTERS, strict=True)
        if _apart(p, drawn) < _apart(p, back) or p == drawn
    )
    return bits, drawn, back


def _shaded(
    blobs: abc.Sequence[clumps.Blob],
    center: tuple[float, float],
    depth: tuple[float, float],
    trunk: int,
    bark: int,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> abc.Iterator[tuple[int, int, str, int, int]]:
    ax, ay = center
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            paints = [
                _paint(blobs, x + qx - ax, y + qy - ay, depth, trunk + 0.5 - ax, bark)
                for qx, qy, _ in _QUARTERS
            ]
            if max(paints) == NONE:
                continue

            bits, drawn, back = _pack(paints)
            yield x, y, QUADRANTS[bits], drawn, back


@functools.lru_cache(maxsize=1024)
def cells(
    blobs: abc.Sequence[clumps.Blob],
    center: tuple[float, float],
    reach: tuple[int, int, int, int],
    trunk: int,
    bark: int = 2,
) -> tuple[tuple[int, int, str, int, int], ...]:
    """Each crown cell as (x, y, char, paint drawn, paint behind or NONE), with *blobs* back to
    front around *center*, and the trunk in column *trunk*, *bark* half cells wide. *reach* bounds the cells to look
    at, (left, top, right, bottom).
    """
    depth = (
        min(by - bry for _, by, _, bry, _ in blobs),
        max(by + bry for _, by, _, bry, _ in blobs),
    )
    left, top, right, bottom = reach
    return tuple(_shaded(blobs, center, depth, trunk, bark, left, top, right, bottom))
