"""Places for tree tags that cover nothing: the crowns, trunks, pennants, signs and buildings
already drawn, other tags, or ground outside the tree's own block.

Saved spots never move, and a tag is as many cells wide at any zoom, so on a small screen tags
run out of room. Each tag tries its row under the crown, then one row lower on a longer trunk, sliding
sideways as far as keeps its trunk under it; failing that, its name gets shorter, down to just
its letter.
"""

import dataclasses
from collections import abc

from ..model import Tree
from . import trees

Rect = tuple[int, int, int, int]  # x, y, w, h
_GAP = 1  # cells kept clear around a tag


@dataclasses.dataclass(frozen=True)
class Tag:
    tree: Tree
    letter: str
    shape: trees.Shape
    ax: float
    ay: float
    bottom: int  # the crown's lowest row; the trunk starts below it
    bounds: tuple[int, int]  # the columns its block spans


@dataclasses.dataclass(frozen=True)
class Fitted:
    lines: tuple[str, ...]
    x: int
    y: int
    trunk: tuple[int, int]  # the trunk's first cell below the crown, (x, row)


def _hits(rect: Rect, taken: abc.Iterable[Rect]) -> bool:
    x, y, w, h = rect
    return any(
        x < ox + ow + _GAP and ox < x + w + _GAP and y < oy + oh and oy < y + h
        for ox, oy, ow, oh in taken
    )


def _widths(tag: Tag) -> list[int]:
    # As long as its whole name where there's room: a tree's shape sizes its tag for spacing
    # trees apart, which stops short of a long name.
    full = max(tag.shape.width, trees.whole_tag(tag.tree, tag.letter))
    least = trees.least_tag(tag.tree, tag.letter)
    return sorted({full, *range(full - 4, least, -4), least}, reverse=True)


def _fit(tag: Tag, taken: list[Rect]) -> Fitted:
    trunk_x = round(tag.ax)
    near = [r for r in taken if r[1] < tag.bottom + 6 and r[1] + r[3] > tag.bottom]  # its rows
    for width in _widths(tag):
        lines = (
            tag.shape.tag
            if width == tag.shape.width
            else (trees.short_tag(tag.tree, tag.letter, width),)
        )
        centered = round(tag.ax - width / 2)
        # Anywhere from the trunk at the tag's right end to the trunk at its left, nearest
        # centered first: the trunk only has to stay under the tag.
        starts = sorted(range(trunk_x - width + 2, trunk_x), key=lambda x: abs(x - centered))
        for drop in (0, 1):
            y = tag.bottom + 2 + drop
            for x in starts:
                if x < tag.bounds[0] or x + width > tag.bounds[1]:
                    continue
                if not _hits((x, y, width, len(lines)), near) and not (
                    drop and _hits((trunk_x, y - 1, 1, 1), near)
                ):
                    return Fitted(lines, x, y, (trunk_x, tag.bottom + 1))

    least = _widths(tag)[-1]
    return Fitted(
        (trees.short_tag(tag.tree, tag.letter, least),),
        round(tag.ax - least / 2),
        tag.bottom + 2,
        (trunk_x, tag.bottom + 1),
    )


def fit(tags: abc.Sequence[Tag], taken: abc.Iterable[Rect]) -> list[Fitted]:
    """A place for each of *tags*, in order, clear of *taken* and of the tags placed before it."""
    placed = list(taken)
    # Each tree keeps the cells under its trunk, so a neighbor's tag can't take its only room.
    under = [(round(tag.ax), tag.bottom + 2, 1, 2) for tag in tags]
    fitted = []
    for i, tag in enumerate(tags):
        found = _fit(tag, [*placed, *under[:i], *under[i + 1 :]])
        placed.append((found.x, found.y, len(found.lines[0]), len(found.lines)))
        fitted.append(found)
    return fitted
