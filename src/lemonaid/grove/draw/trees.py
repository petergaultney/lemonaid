"""A tree: a crown of overlapping ellipses in quadrant blocks, a trunk, lemons, and a two-line tag."""

import dataclasses
import functools
from collections import abc

from ..model import Tree
from . import colors, hanging
from .canvas import QUADRANTS, Canvas, box, mix, put, text, wide
from .ground import noise, word_hash


@dataclasses.dataclass(frozen=True)
class Shape:
    rx: float
    ry: float
    blobs: tuple[
        tuple[float, float, float, float], ...
    ]  # (dx, dy, rx, ry) around the crown's center
    width: int  # the footprint, crown or tag, whichever is wider
    height: int
    top: int  # rows from the footprint's top to the crown's center
    tag: tuple[str, ...]


def _head(letter: str, lead: bool) -> str:
    """A tag's start: its key on a cap with a cell either side, then a cell in the tag's own
    colors, so neither the key nor the name meets the change of color."""
    return f" {letter}  {'★ ' if lead else ''}"


def _tag_lines(letter: str, label: str, lead: bool, width: int) -> tuple[str, ...]:
    lines = [_head(letter, lead)[1:]]
    for word in label.split():
        if len(lines[-1].strip()) > 3 and len(lines[-1] + word) > width - 2:
            lines.append("  " + word + " ")
        else:
            lines[-1] += word + " "
    if len(lines) > 2:
        lines[1:] = [lines[1].rstrip()[: width - 4] + "… "]
    fitted = [line if len(line) < width else line.rstrip()[: width - 3] + "… " for line in lines]
    return tuple((" " + line)[:width].ljust(width) for line in fitted)


@functools.lru_cache(maxsize=4096)
def shape(tree: Tree, letter: str, size: float, full_tag: bool = False) -> Shape:
    """*size* scales the crown: about 1 for a grown tree, smaller for a sapling or a crowded block."""
    n = min(len(tree.lemons), 5)
    seed = word_hash(tree.key)

    def jitter(k: int) -> float:
        return noise(seed, k) - 0.5

    rx = max(2.4, (3.4 + n * 1.1 + (1.4 if tree.lead else 0)) * size)
    # Tall enough for a row per lemon at any size, so lemons hang alike zoomed in and out.
    ry = max(0.95, 0.6 * n + 0.5, (1.2 + n * 0.18 + (0.4 if tree.lead else 0)) * size)
    blobs = (
        (0.0, 0.0, rx, ry),
        (-rx * (0.45 + 0.1 * jitter(1)), -ry * (0.35 + 0.15 * jitter(2)), rx * 0.58, ry * 0.8),
        (rx * (0.42 + 0.1 * jitter(3)), -ry * (0.3 + 0.15 * jitter(4)), rx * 0.55, ry * 0.75),
        (rx * 0.1 * jitter(5), -ry * 0.75, rx * 0.45, ry * 0.6),
    )
    # Room at the tag's end for the emoji and the pin, so neither covers the name.
    marks = (3 if any(lemon.emoji for lemon in tree.lemons) else 0) + (
        1 if any(lemon.pinned for lemon in tree.lemons) else 0
    )
    one_line = not full_tag  # the grove view: one row a tree
    name = (
        len(tree.label) + 8
        if full_tag
        else min(len(tree.label) + 7, 23)
        if one_line
        else min(len(tree.label) + 8, 21)
    )
    width = max(int(rx * 2) + 4, name + marks)
    if one_line:
        whole = f"{_head(letter, tree.lead)}{tree.label} "
        fit = width - marks
        tag: tuple[str, ...] = (
            (whole if len(whole) <= fit else whole[: fit - 2] + "… ").ljust(width),
        )
    else:
        tag = tuple(
            line.ljust(width) for line in _tag_lines(letter, tree.label, tree.lead, width - marks)
        )
    top = int(ry * 1.4) + 2
    return Shape(rx, ry, blobs, width, top + int(ry) + 3 + len(tag), top, tag)


def _in_crown(s: Shape, dx: float, dy: float) -> bool:
    return any(((dx - bx) / brx) ** 2 + ((dy - by) / bry) ** 2 <= 1 for bx, by, brx, bry in s.blobs)


_QUARTERS = ((0.25, 0.25, 1), (0.75, 0.25, 2), (0.25, 0.75, 4), (0.75, 0.75, 8))


def _cells(s: Shape, ax: float, ay: float) -> abc.Iterator[tuple[int, int, int]]:
    """Each crown cell centered on (*ax*, *ay*), with its quadrant bits."""
    for y in range(int(ay - s.ry * 1.45) - 1, int(ay + s.ry) + 2):
        for x in range(int(ax - s.rx) - 1, int(ax + s.rx) + 2):
            bits = sum(bit for qx, qy, bit in _QUARTERS if _in_crown(s, x + qx - ax, y + qy - ay))
            if bits:
                yield x, y, bits


# Where a trunk leaves its crown, a live tree's or a bare one's; a single column runs on below.
FLARE = "\u259c\u2588\u259b"  # "▜█▛"


def _bottom(s: Shape, ax: float, ay: float) -> int:
    """The crown's lowest row over the trunk, where the trunk starts below."""
    return max(
        (y for x, y, bits in _cells(s, ax, ay) if abs(x - ax) < 1 and bits & 12), default=int(ay)
    )


def _crown(
    canvas: Canvas, s: Shape, ax: float, ay: float, leaf: tuple[str, str]
) -> tuple[list[tuple[int, int]], int]:
    """Draw the crown centered on (*ax*, *ay*); return its solid cells and the row of its lowest edge."""
    solid: list[tuple[int, int]] = []
    for x, y, bits in _cells(s, ax, ay):
        put(canvas, x, y, QUADRANTS[bits], leaf[0] if y < ay - s.ry * 0.15 else leaf[1])
        if bits == 15:
            solid.append((x, y))
    return solid, _bottom(s, ax, ay)


def crown_box(s: Shape, ax: float, ay: float) -> tuple[int, int, int, int]:
    """The crown and its trunk's first cell, (x, y, w, h)."""
    cells = list(_cells(s, ax, ay))
    left = min(x for x, _, _ in cells)
    top = min(y for _, y, _ in cells)
    return left, top, max(x for x, _, _ in cells) - left + 1, _bottom(s, ax, ay) + 2 - top


def pennant_box(s: Shape, ax: float, ay: float) -> tuple[int, int, int, int]:
    top = min(y for _, y, _ in _cells(s, ax, ay))
    return round(ax), top - 2, 4, 2


def _marks(tree: Tree) -> int:
    """Cells at the tag's end for the emoji and the pin."""
    return (3 if any(lemon.emoji for lemon in tree.lemons) else 0) + (
        1 if any(lemon.pinned for lemon in tree.lemons) else 0
    )


def whole_tag(tree: Tree, letter: str) -> int:
    """The one-line tag's width with all of its name, and room for the emoji and pin."""
    return len(f"{_head(letter, tree.lead)}{tree.label} ") + _marks(tree)


def least_tag(tree: Tree, letter: str) -> int:
    """The narrowest tag: its letter, and room for the emoji and pin after it."""
    return len(_head(letter, tree.lead)) + _marks(tree)


def short_tag(tree: Tree, letter: str, width: int) -> str:
    """The one-line tag cut to *width*: the name shortened, down to just the letter."""
    marks = _marks(tree)
    head = _head(letter, tree.lead)
    room = width - marks - len(head) - 1
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
        under = leaf[0] if y < ay - s.ry * 0.15 else leaf[1]
        if lemon.channel in hits:
            put(canvas, x, y, "◉", "#ffffff", under, bold=True)
        elif lemon.status == "done":
            put(canvas, x, y, "∘", mix(under, "#ffffff", 0.18), under)
        else:
            put(
                canvas,
                x,
                y,
                colors.lemon_glyph(lemon),
                colors.lemon_color(lemon, phase),
                under,
                bold=True,
            )

    trunk_x = round(ax)
    if pennant:
        x, y, _, _ = pennant_box(s, ax, ay)
        put(canvas, x, y + 1, "│", colors.TRUNK)
        put(canvas, x, y, "│", colors.TRUNK)
        put(canvas, x + 1, y, "█", pennant)
        put(canvas, x + 2, y, "▀", pennant)
        put(canvas, x + 3, y, "▘", pennant)
    text(canvas, trunk_x - 1, bottom + 1, FLARE, colors.TRUNK)
    return bottom


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
) -> None:
    """The tag's *lines* with their top left at (*x*, *y*), and the trunk from its *trunk* cell
    (x, row) down to the tag. Its first *key* characters after the leading space are the key,
    drawn on a cap with a cell either side.
    """
    for row in range(trunk[1], y):
        put(canvas, trunk[0], row, "█", colors.TRUNK)
    width = len(lines[0])
    status = colors.tree_status(tree.lemons)
    working = any(lemon.working for lemon in tree.lemons)
    tag_bg = mix(colors.STATUS.get(status, colors.TAG), "#0b0e13", 0.75 * phase if working else 0)
    tag_fg = colors.on_status(status) if status else colors.TEXT
    for i, line in enumerate(lines):
        text(canvas, x, y + i, line, tag_fg, tag_bg, bold=i == 0)
    # The letter to type, on a cap in the tag's colors swapped, as a packhouse bay's is. An
    # underline would be drawn in the text's color, which some terminals lose against the row below.
    text(canvas, x, y, lines[0][: key + 2], tag_bg, tag_fg, bold=True)
    emoji = next((lemon.emoji for lemon in tree.lemons if lemon.emoji), "")
    if emoji:
        wide(canvas, x + width - 3, y, emoji, tag_fg, tag_bg)
    if any(lemon.pinned for lemon in tree.lemons):
        put(canvas, x + width - 1, y + len(lines) - 1, "▪", tag_fg, tag_bg)
    if selected:
        box(canvas, x - 1, y - 1, width + 2, len(lines) + 2, "#ffffff")
