"""Where lemons hang on a crown."""

import math
from collections import abc

from .ground import noise

Cell = tuple[int, int]


def _places(count: int, seed: int) -> list[tuple[float, float]]:
    """Where each lemon hangs, as fractions of the crown's radii from its center: top to bottom,
    a row each, alternating sides. Relative to the crown, so a lemon keeps its place at any zoom.
    """
    first_side = 1 if noise(seed, 1) > 0.5 else -1
    return [
        (
            first_side * (-1) ** i * (0.15 + 0.45 * noise(seed, i + 2)),
            -0.75 + 1.2 * i / (count - 1) if count > 1 else -0.25,
        )
        for i in range(count)
    ]


def _cost(
    cell: Cell, target: tuple[float, float], chosen: abc.Sequence[Cell], inside: abc.Container[Cell]
) -> float:
    """Distance from a lemon's place, plus prices: for a cell at the crown's edge, without
    leaves on every side; for touching another lemon; and for sharing a row, small beside
    another lemon, as a bunch, and prohibitive apart from it, where two read as eyes.
    """
    x, y = cell
    shared = [cx for cx, cy in chosen if cy == y]
    crowd = 0 if not shared else 6 if any(abs(cx - x) == 1 for cx in shared) else 1000
    touching = 5 if any(abs(cx - x) <= 1 and abs(cy - y) <= 1 for cx, cy in chosen) else 0
    edge = 0 if cell in inside else 3
    return math.hypot(x + 0.5 - target[0], (y + 0.5 - target[1]) * 2) + crowd + touching + edge


def spots(
    solid: abc.Iterable[Cell],
    center: tuple[float, float],
    radii: tuple[float, float],
    count: int,
    seed: int,
) -> list[Cell]:
    """The solid crown cell nearest each lemon's place, a row each while rows last, inside
    the crown where it can be.
    """
    (ax, ay), (rx, ry) = center, radii
    leaves = set(solid)
    inside = {
        (x, y) for x, y in leaves if {(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)} <= leaves
    }
    free = [(x, y) for x, y in leaves if not (abs(x - ax) <= 0.6 and y >= ay - 0.5)]  # trunk
    chosen: list[Cell] = []
    for u, v in _places(count, seed):
        options = [cell for cell in free if cell not in chosen]
        if not options:
            break

        chosen.append(
            min(options, key=lambda cell: _cost(cell, (ax + u * rx, ay + v * ry), chosen, inside))
        )
    return chosen
