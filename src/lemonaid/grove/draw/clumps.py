"""Where a crown's leaf clumps go, each lit by where it is on the crown."""

import math
from collections import abc

# (dx, dy, rx, ry) around the crown's center, and how much of the light reaches it, 0 to 1
Blob = tuple[float, float, float, float, float]


# The largest a clump grows: a grown tree's, so a bigger crown gets more clumps rather than
# bigger ones and keeps the same leafy detail.
_BIGGEST = 4.8


def _filling(
    rx: float, tall: float, size: float, jitter: abc.Callable[[int], float]
) -> abc.Iterator[tuple[float, float, float]]:
    """(x, y, scale) of clumps packed through a crown too big for its ring to cover, staggered
    rows of them, as if a row were as tall as a cell is wide.
    """
    across, down = 1.3 * size, 1.1 * size
    rows = int((1.3 * tall - size) / down)
    for row in range(rows + 1):
        y = -tall + size + row * down
        half = (rx - size) * math.sqrt(max(0.0, 1 - (y / tall) ** 2))
        for col in range(-int(half / across) - 1, int(half / across) + 2):
            x = (col + 0.5 * (row % 2)) * across
            k = 1000 + 64 * row + 2 * col
            if abs(x) <= half:
                yield x + 0.25 * across * jitter(k), y, 0.85 + 0.3 * jitter(k + 1)


def crown(rx: float, ry: float, jitter: abc.Callable[[int], float]) -> tuple[Blob, ...]:
    """A crown *rx* across and *ry* down, from its center to its edges, as clumps back to front:
    one filling the middle, a ring of clumps around a dome, one or two inside it (rows of them in
    a crown bigger than a grown tree), and a shallow, uneven arc of them underneath. Clumps lower down get less of the light, some more and some
    less. *jitter*, from -0.5 to 0.5, varies them.
    """
    # Worked out as if a row were as tall as a cell is wide, so clumps are round on screen.
    cy, tall = -0.25 * ry, 2 * 1.1 * ry
    size = min(0.5 * min(rx, tall), _BIGGEST)
    count = max(3, round(1.8 * rx / size))
    beneath = max(3, 1 + round(1.1 * rx / (1.3 * size)))

    def clump(x: float, y: float, scale: float) -> tuple[float, float, float, float, float]:
        r = size * scale
        shine = jitter(5000 + 37 * round(4 * x / rx) + round(8 * y / tall))
        lit = 0.5 - 0.45 * x / rx - 0.6 * y / tall - 0.7 * max(0.0, y / tall + 0.1)
        lit = min(1.0, max(0.0, lit + 0.4 * shine))
        return x, cy + y / 2, r, r / 2, lit

    ring = [
        clump((rx - r) * math.cos(angle), (tall - r) * math.sin(angle), scale)
        for i in range(count)
        # From the left side over the top to the right side, each clump's edge on the crown's.
        for angle in (math.radians(175 + 190 * (i + 0.5 + 0.4 * jitter(3 * i)) / count),)
        for scale in (0.95 + 0.35 * jitter(3 * i + 1),)
        for r in (size * scale,)
    ]
    inside = (
        [
            clump(0.5 * rx * jitter(40 + 2 * i), tall * (0.3 * jitter(41 + 2 * i) - 0.1), 0.8)
            for i in range(1 if rx < 5 else 2)
        ]
        if size < _BIGGEST
        else [clump(*at) for at in _filling(rx, tall, size, jitter)]
    )
    # Wide and squat, so the crown is flatter underneath than on top.
    under = [
        (bx, by, brx, bry * 0.8, lit)
        for i in range(beneath)
        for x in ((2 * i / (beneath - 1) - 1) * 0.55 * rx + 0.06 * rx * jitter(50 + i),)
        for bx, by, brx, bry, lit in (
            clump(
                x,
                (0.5 - 0.15 * (x / (0.55 * rx)) ** 2 + 0.08 * jitter(60 + i)) * tall,
                0.8 + 0.05 * (x == 0),
            ),
        )
    ]
    behind = (0.0, cy - 0.05 * tall, 0.86 * rx, 0.7 * tall / 2, 0.45)
    return (behind, *sorted((*ring, *inside, *under), key=lambda blob: blob[1]))
