"""Where a tree's list goes in a zoomed block: at its own tree, so its title, the tree's tag,
reads as that tree's and no other's.
"""

import math
from collections import abc

from . import tag_fit
from .canvas import Canvas

Rect = tuple[int, int, int, int]
GAP = 2  # columns kept clear beside a list; one row above and below
COVER_PER_COLUMN = 4  # cells covered that count as one more column from the tree


def footprint(crown: Rect, tag: tag_fit.Fitted) -> Rect:
    """A tree's crown and its tag together."""
    x, y, w, _ = crown
    left, right = min(x, tag.x), max(x + w, tag.x + len(tag.lines[0]))
    return left, y, right - left, tag.y + len(tag.lines) - y


def overlap(a: Rect, others: abc.Iterable[Rect]) -> int:
    x, y, w, h = a
    return sum(
        max(0, min(x + w, ox + ow) - max(x, ox)) * max(0, min(y + h, oy + oh) - max(y, oy))
        for ox, oy, ow, oh in others
    )


def _kept_clear(taken: abc.Iterable[Rect]) -> list[Rect]:
    return [(x - GAP, y - 1, w + 2 * GAP, h + 2) for x, y, w, h in taken]


def crowding(canvas: Canvas, rect: Rect, taken: abc.Iterable[Rect]) -> float:
    """How much of *taken*, and the room kept around it, *rect* covers; off the screen, too much."""
    x, y, w, h = rect
    if not (x >= 1 and x + w <= canvas.width - 1 and y >= 1 and y + h <= canvas.height - 1):
        return math.inf

    return overlap(rect, _kept_clear(taken))


def _apart(a: Rect, b: Rect) -> float:
    """The gap between *a* and *b*, a row counting as two columns, as a cell is twice as tall."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return math.hypot(max(0, bx - ax - aw, ax - bx - bw), 2 * max(0, by - ay - ah, ay - by - bh))


def title_at(tag_x: int, x: int, w: int, title: int) -> int:
    """The column of a *title*-wide title on the top border of a list at *x*, *w* wide: under the
    tree's tag at *tag_x* when the border reaches it, else as near as the border gets.
    """
    return min(max(tag_x, x + 1), x + w - 1 - title)


def _beside(
    crown: Rect, tag: tag_fit.Fitted, height: int, width: int, w: int
) -> list[tuple[int, int, bool]]:
    """Spots for a list at its tree, best first, each saying whether the list hangs from the tag,
    where it may cover the tag as its title shows it. A hanging list's title slides along its top
    border to sit under the tree, so the list may extend right from the tag, or left from it.
    After those come spots across the screen's width, on rows around the crown, for a crowded
    block to use the room beside it: `spot` picks the nearest.
    """
    cx, cy, cw, ch = crown
    end = tag.x + len(tag.lines[0]) + 1
    return [
        *((tag.x - 1 - slide, tag.y, True) for slide in (0, 2, 4)),
        *((end - w + slide, tag.y, True) for slide in (0, 2, 4)),
        (tag.x - 1, cy - height - 1, False),
        *((cx + cw + GAP, y, False) for y in range(cy, cy + ch)),
        *(
            (x, y, False)
            for y in range(cy - height, cy + ch + height + 1, 2)
            for x in range(1, width - w, 3)
        ),
    ]


def spot(
    canvas: Canvas,
    crown: Rect,
    tag: tag_fit.Fitted,
    others: abc.Sequence[Rect],
    w: int,
    height: int,
    taken: abc.Sequence[Rect],
    caps: abc.Sequence[Rect] = (),
) -> tuple[int, int]:
    """The spot at its tree whose list covers least of *taken*, its own crown and tag, and the room
    kept around the rest. A list never covers its own crown when another spot avoids it, nor puts
    its title nearer another tree than its own if it can help it, and covers as little as it can
    of *caps*, the letters of other lists' titles. Otherwise a spot's cost is its title's distance
    from its tree in columns plus the cells it covers over `COVER_PER_COLUMN`, so a list covers a
    neighbor a little before it goes far from its tree. Spots at the tree that cover nothing keep
    `_beside`'s order.
    """
    own = footprint(crown, tag)
    clear = _kept_clear(r for r in taken if r != own)
    tagged = (
        tag.x,
        tag.y,
        len(tag.lines[0]),
        len(tag.lines),
    )  # a list hanging from it may cover it

    def cost(i: int, x: int, y: int, hangs: bool) -> tuple[int, bool, bool, float, int]:
        tlen = len(tag.lines[0])
        rect, title = (x, y, w, height), (title_at(tag.x, x, w, tlen), y, tlen, 1)
        covers = overlap(rect, [*clear, crown, *(() if hangs else (tagged,))])
        astray = min((_apart(title, o) for o in others), default=math.inf) < _apart(title, own)
        away = _apart(title, own)
        score = 0.0 if i < 7 + crown[3] and not covers else away + covers / COVER_PER_COLUMN
        return overlap(rect, caps), overlap(rect, [crown]) > 0, astray, score, i

    _, x, y, _ = min(
        (
            (
                i,
                min(max(1, x), canvas.width - w - 1),
                min(max(1, y), canvas.height - height - 2),
                hangs,
            )
            for i, (x, y, hangs) in enumerate(_beside(crown, tag, height, canvas.width, w))
        ),
        key=lambda s: cost(*s),
    )
    return x, y
