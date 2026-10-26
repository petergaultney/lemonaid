"""A tree: a crown of overlapping ellipses in quadrant blocks, a trunk, lemons, and a two-line tag."""

import dataclasses
import functools
from collections import abc

from ..model import Tree
from . import clumps, colors, crown, hanging
from .canvas import QUADRANTS, Canvas, box, mix, put, text, wide
from .ground import noise, word_hash


@dataclasses.dataclass(frozen=True)
class Shape:
    rx: float  # the room the crown takes, across and down, which the layout keeps clear
    ry: float
    blobs: tuple[clumps.Blob, ...]  # leaf clumps, back to front
    bark: int  # the trunk's width in half cells
    width: int  # the footprint, crown or tag, whichever is wider
    height: int
    top: int  # rows from the footprint's top to the crown's center
    tag: tuple[str, ...]


def _head(letter: str, lead: bool, emoji: str) -> str:
    """A tag's start: its key on a cap with a cell either side, then a cell in the tag's own
    colors, so neither the key nor the name meets the change of color; then the lead's crown and
    two cells that `draw_tag` fills with *emoji*, as a lemon list's row has them.
    """
    return f" {letter}  {'♛ ' if lead else ''}{'   ' if emoji else ''}"


def _emoji(tree: Tree) -> str:
    return tree.lemons[0].emoji


def _tag_lines(letter: str, label: str, lead: bool, emoji: str, width: int) -> tuple[str, ...]:
    lines = [_head(letter, lead, emoji)[1:]]
    for word in label.split():
        if len(lines[-1].strip()) > 3 and len(lines[-1] + word) > width - 2:
            lines.append("  " + word + " ")
        else:
            lines[-1] += word + " "
    if len(lines) > 2:
        lines[1:] = [lines[1].rstrip()[: width - 4] + "… "]
    fitted = [line if len(line) < width else line.rstrip()[: width - 3] + "… " for line in lines]
    return tuple((" " + line)[:width].ljust(width) for line in fitted)


# A grown tree's crown height from its center; taller crowns read as blobs.
GROWN = 4.4


@functools.lru_cache(maxsize=4096)
def shape(
    tree: Tree, letter: str, size: float, full_tag: bool = False, tallest: float = GROWN
) -> Shape:
    """*size* scales the crown: about 1 for a grown tree, smaller for a sapling or a crowded block.
    The crown grows no taller than *tallest* rows from its center, unless its lemons need more.
    """
    n = min(len(tree.lemons), 5)
    seed = word_hash(tree.key)

    def jitter(k: int) -> float:
        return noise(seed, k) - 0.5

    # Tall enough for a row per lemon at any size, so lemons hang alike zoomed in and out.
    ry = max(1.35, 0.6 * n + 0.5, min((1.2 + n * 0.18 + (0.4 if tree.lead else 0)) * size, tallest))
    # Wide as a citrus tree, but only round once its lemons make it tall, so a crowded block
    # still has room for it; and never so wide it reads as a cloud.
    rx = min(
        max(2.4, (3.4 + n * 1.1 + (1.4 if tree.lead else 0)) * size, 2.4 * min(ry, 2.6)),
        2.8 * ry,
    )
    blobs = clumps.crown(rx, ry, jitter)
    emoji = _emoji(tree)
    one_line = not full_tag  # the grove view: one row a tree
    name = (
        len(tree.label) + 8
        if full_tag
        else min(len(tree.label) + 7, 23)
        if one_line
        else min(len(tree.label) + 8, 21)
    )
    width = max(int(rx * 2) + 4, name + (3 if emoji else 0))
    if one_line:
        whole = f"{_head(letter, tree.lead, emoji)}{tree.label} "
        tag: tuple[str, ...] = (
            (whole if len(whole) <= width else whole[: width - 2] + "… ").ljust(width),
        )
    else:
        tag = tuple(
            line.ljust(width) for line in _tag_lines(letter, tree.label, tree.lead, emoji, width)
        )
    top = int(ry * 1.4) + 2
    return Shape(
        rx,
        ry,
        blobs,
        2 if rx < 7 else 4 if rx < 13 else 6,
        width,
        top + int(ry) + 3 + len(tag),
        top,
        tag,
    )


def _in_crown(s: Shape, dx: float, dy: float) -> bool:
    return any(
        ((dx - bx) / brx) ** 2 + ((dy - by) / bry) ** 2 <= 1 for bx, by, brx, bry, _ in s.blobs
    )


_QUARTERS = ((0.25, 0.25, 1), (0.75, 0.25, 2), (0.25, 0.75, 4), (0.75, 0.75, 8))


def _reach(s: Shape, ax: float, ay: float) -> tuple[int, int, int, int]:
    """The cells the crown centered on (*ax*, *ay*) can reach: (left, top, right, bottom)."""
    return (
        int(ax + min(bx - brx for bx, _, brx, _, _ in s.blobs)) - 1,
        int(ay + min(by - bry for _, by, _, bry, _ in s.blobs)) - 1,
        int(ax + max(bx + brx for bx, _, brx, _, _ in s.blobs)) + 1,
        int(ay + max(by + bry for _, by, _, bry, _ in s.blobs)) + 1,
    )


# Kept, as the crown's shading is: a pulsing grove draws the same crowns many times over.
@functools.lru_cache(maxsize=1024)
def _cells(s: Shape, ax: float, ay: float) -> tuple[tuple[int, int, int], ...]:
    """Each crown cell centered on (*ax*, *ay*), with its quadrant bits."""
    left, top, right, bottom = _reach(s, ax, ay)
    return tuple(
        (x, y, bits)
        for y in range(top, bottom + 1)
        for x in range(left, right + 1)
        for bits in (
            sum(bit for qx, qy, bit in _QUARTERS if _in_crown(s, x + qx - ax, y + qy - ay)),
        )
        if bits
    )


def _bottom(s: Shape, ax: float, ay: float) -> int:
    """The crown's lowest row, where the trunk leaves it."""
    return max((y for _, y, bits in _cells(s, ax, ay) if bits & 12), default=int(ay))


def _crown(
    canvas: Canvas, s: Shape, ax: float, ay: float, leaf: abc.Sequence[str]
) -> tuple[dict[tuple[int, int], str], int]:
    """Draw the crown centered on (*ax*, *ay*) in *leaf*'s shades, darkest first; return its
    solid cells, each with the shade a lemon hangs on there, and the row of its lowest edge.
    """
    solid = {}
    bottom = _bottom(s, ax, ay)
    paint = (*leaf, colors.TRUNK, colors.TRUNK_SHADE)
    reach = (*_reach(s, ax, ay)[:3], bottom)
    for x, y, char, drawn, back in crown.cells(s.blobs, (ax, ay), reach, round(ax), s.bark):
        put(canvas, x, y, char, paint[drawn], paint[back] if back != crown.NONE else None)
        if crown.NONE != back < crown.BARK and drawn < crown.BARK:
            solid[(x, y)] = paint[drawn] if QUADRANTS.index(char).bit_count() >= 2 else paint[back]
    return solid, bottom


def crown_box(s: Shape, ax: float, ay: float) -> tuple[int, int, int, int]:
    """The crown and its trunk's first cell, (x, y, w, h)."""
    cells = list(_cells(s, ax, ay))
    left = min(x for x, _, _ in cells)
    top = min(y for _, y, _ in cells)
    return left, top, max(x for x, _, _ in cells) - left + 1, _bottom(s, ax, ay) + 2 - top


def pennant_box(s: Shape, ax: float, ay: float) -> tuple[int, int, int, int]:
    top = min(y for _, y, _ in _cells(s, ax, ay))
    return round(ax), top - 2, 4, 2


def whole_tag(tree: Tree, letter: str) -> int:
    """The one-line tag's width with all of its name."""
    return len(f"{_head(letter, tree.lead, _emoji(tree))}{tree.label} ")


def least_tag(tree: Tree, letter: str) -> int:
    """The narrowest tag: its letter, crown and emoji."""
    return len(_head(letter, tree.lead, _emoji(tree)))


def short_tag(tree: Tree, letter: str, width: int) -> str:
    """The one-line tag cut to *width*: the name shortened, down to just the letter."""
    head = _head(letter, tree.lead, _emoji(tree))
    room = width - len(head) - 1
    name = tree.label if len(tree.label) <= room else tree.label[: max(0, room - 1)] + "…"
    return (head + name if room > 0 else head).ljust(width)


def draw(
    canvas: Canvas,
    tree: Tree,
    s: Shape,
    ax: float,
    ay: float,
    phase: float,
    hits: abc.Container[str] = (),
    pennant: str = "",
) -> int:
    """Draw *tree*'s crown, lemons and trunk, centered on (*ax*, *ay*); return the crown's
    bottom row. *hits* are channels a search matched; *pennant*, a color, flies a pennant from
    the crown, which marks the block's lead. The tag is drawn by `draw_tag`, once it has a place.
    """
    leaf = colors.LEAD_LEAF if tree.lead else colors.LEAF
    solid, bottom = _crown(canvas, s, ax, ay, leaf)
    for lemon, (x, y) in zip(
        tree.lemons,
        hanging.spots(solid, (ax, ay), (s.rx, s.ry), len(tree.lemons), word_hash(tree.key)),
        strict=False,
    ):
        if lemon.channel in hits:
            put(canvas, x, y, "◉", "#ffffff", solid[(x, y)], bold=True)
        else:
            put(
                canvas,
                x,
                y,
                colors.lemon_glyph(lemon),
                colors.lemon_color(lemon, phase),
                solid[(x, y)],
                bold=True,
            )
    if pennant:
        x, y, _, _ = pennant_box(s, ax, ay)
        put(canvas, x, y + 1, "│", colors.TRUNK)
        put(canvas, x, y, "│", colors.TRUNK)
        put(canvas, x + 1, y, "█", pennant)
        put(canvas, x + 2, y, "▀", pennant)
        put(canvas, x + 3, y, "▘", pennant)
    return bottom


def _bark(x: int, bark: int) -> abc.Iterator[tuple[int, str, str, str | None]]:
    """A row of trunk *bark* half cells wide around column *x*'s middle, lit on its left: each
    cell's (column, char, color, color behind).
    """
    for column in range(x - 1, x + 2):
        left, right = (
            (colors.TRUNK if half < x + 0.5 else colors.TRUNK_SHADE)
            if abs(half - x - 0.5) < bark / 4
            else None
            for half in (column + 0.25, column + 0.75)
        )
        if left and right:
            yield column, "█" if left == right else "▌", left, right if left != right else None
        elif left or right:
            yield column, "▌" if left else "▐", left or right, None


def draw_tag(
    canvas: Canvas,
    tree: Tree,
    lines: abc.Sequence[str],
    x: int,
    y: int,
    trunk: tuple[int, int],
    phase: float,
    selected: bool = False,
    key: int = 1,
    bark: int = 2,
) -> None:
    """The tag's *lines* with their top left at (*x*, *y*), and the trunk from its *trunk* cell
    (x, row) down to the tag, *bark* half cells wide. Its first *key* characters after the leading space are the key,
    drawn on a cap with a cell either side.
    """
    for row in range(trunk[1], y):
        for column, char, fg, bg in _bark(trunk[0], bark):
            put(canvas, column, row, char, fg, bg)
    width = len(lines[0])
    status = colors.tree_status(tree.lemons)
    working = any(lemon.working for lemon in tree.lemons)
    tag_bg = mix(
        colors.STATUS.get(status, colors.TAG),
        "#0b0e13",
        colors.PULSE_DEPTH * phase if working else 0,
    )
    tag_fg = colors.on_status(status) if status else colors.TEXT
    for i, line in enumerate(lines):
        text(canvas, x, y + i, line, tag_fg, tag_bg, bold=i == 0)
    # The letter to type, on a cap in the tag's colors swapped, as a packhouse bay's is. An
    # underline would be drawn in the text's color, which some terminals lose against the row below.
    text(canvas, x, y, lines[0][: key + 2], tag_bg, tag_fg, bold=True)
    emoji = _emoji(tree)
    if emoji:
        wide(canvas, x + key + 3 + (2 if tree.lead else 0), y, emoji, tag_fg, tag_bg)
    if selected:
        box(canvas, x - 1, y - 1, width + 2, len(lines) + 2, "#ffffff")
    if tree.lemons[0].pinned:  # over a selection's outline, which takes the same cell
        put(canvas, x - 1, y, "▐", colors.TEXT)
