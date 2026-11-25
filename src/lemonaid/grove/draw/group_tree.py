"""A group drawn as one tree, in trees scale: its lemons hang in one crown, and a list beside it
gives each lemon's letter and name.
"""

from collections import abc

from ..layout.arrange import Arrangement
from ..model import Block, Tree
from . import colors, lemon_list, trees
from .canvas import BACKGROUND, Canvas, put, text, wide
from .plots import View

_SIZES = (4.0, 3.2, 2.6, 2.2, 1.8, 1.5, 1.2, 1.0, 0.8, 0.6, 0.45)
_TRUNK = 6  # rows of trunk under a zoomed group's crown


def _crown_tree(block: Block) -> Tree:
    return Tree(
        f"{block.digit} {block.name or 'no group'}",
        block.name or "no group",
        tuple(t.lemons[0] for t in block.trees),
        False,
    )


def _shape(tree: Tree, width: int, height: int) -> trees.Shape:
    """The largest crown that fits *width* columns and *height* rows, sign and trunk included."""
    tallest = max(1.35, (height - 5) / 2)
    for size in _SIZES:
        shape = trees.shape(tree, "", size, False, tallest)
        if 2 * shape.rx + 2 <= width and shape.top + shape.ry + 4 <= height:
            return shape
    return trees.shape(tree, "", _SIZES[-1], False, tallest)


def _trunk_and_sign(
    canvas: Canvas, block: Block, shape: trees.Shape, ax: float, bottom: int, ground: int
) -> None:
    trees.draw_trunk(canvas, (round(ax), bottom + 1), ground, shape.bark)
    reach = round(shape.rx) + 2
    for col in range(round(ax) - reach, round(ax) + reach + 1):
        put(canvas, col, ground, "▀", block.color)
    sign = f" {block.digit} {(block.name or 'no group').upper()} "
    text(canvas, round(ax) - len(sign) // 2, ground + 1, sign, BACKGROUND, block.color, bold=True)


def _row(
    canvas: Canvas,
    block: Block,
    tree: Tree,
    letter: str,
    label: str,
    x: int,
    y: int,
    width: int,
    phase: float,
) -> None:
    lemon = tree.lemons[0]
    indent = 0 if tree.key == tree.branch else 2  # a reviewer, under its session's main lemon
    canvas.target = (block.digit, letter)
    status = colors.tree_status(tree.lemons)
    key = f" {letter} "
    if background := colors.fill(status):
        text(canvas, x + indent, y, key, colors.on_status(status), background, bold=True)
    else:
        text(canvas, x + indent, y, key, colors.TAG, colors.TEXT, bold=True)
    if lemon.pinned:
        put(canvas, x + indent - 1, y, "▐", colors.TEXT)
    at = x + indent + len(key) + 1
    if lemon.emoji:
        wide(canvas, at, y, lemon.emoji, colors.TEXT)
        at += 3
    put(canvas, at, y, colors.lemon_glyph(lemon), colors.lemon_color(lemon, phase), bold=True)
    text(canvas, at + 2, y, label, colors.TEXT, bold=tree.lead, limit=x + width - at - 2)
    canvas.target = ()


def draw(
    canvas: Canvas,
    block: Block,
    arrangement: Arrangement,
    view: View,
    phase: float,
    fade: abc.Callable[[Tree], float],
    hits: abc.Container[str] = (),
) -> tuple[int, int, int, int]:
    """Draw *block* as one tree in its plot, in the grove view; return where it is (x, y, w, h)."""
    plot = arrangement.plots[block.name]
    x0, y0 = (round(v) for v in view.screen(plot.x, plot.y))
    x1, y1 = (round(v) for v in view.screen(plot.x + plot.w, plot.y + plot.h))
    w, h = max(20, x1 - x0), max(8, y1 - y0)
    crown = _crown_tree(block)
    shape = _shape(crown, w // 2, h)
    ax, ay = x0 + shape.rx + 1, y0 + shape.top - 1
    canvas.target = (block.digit,)
    bottom = trees.draw(canvas, crown, shape, ax, ay, phase, hits)
    _trunk_and_sign(canvas, block, shape, ax, bottom, y0 + h - 2)
    canvas.target = ()
    left = round(ax + shape.rx) + 3
    rows = h - 1
    for i, tree in enumerate(block.trees[:rows]):
        if i == rows - 1 and len(block.trees) > rows:
            text(canvas, left, y0 + i, f"+{len(block.trees) - i} more", colors.MUTED)
            break
        standing = arrangement.trees[(block.name, tree.key)]
        canvas.dim = fade(tree)
        _row(
            canvas, block, tree, standing.letter, standing.label, left, y0 + i, x0 + w - left, phase
        )
        canvas.dim = 0.0
    return x0, y0, w, h


def _claim(canvas: Canvas, x: int, y: int, width: int, target: tuple[str, ...]) -> None:
    """Make a click on row *y* from *x* choose *target*."""
    if 0 <= y < canvas.height:
        for col in range(max(0, x), min(canvas.width, x + width)):
            canvas.rows[y][col].target = target


def zoomed(
    canvas: Canvas,
    block: Block,
    arrangement: Arrangement,
    phase: float,
    hits: abc.Container[str] | None,
    opened: str,
    edited: str = "",
    flipped: bool = False,
) -> dict[str, tuple[int, int, int, int]]:
    """*block*'s tree filling the screen, its lemons listed beside it; returns each lemon's row."""
    across = lemon_list.width(canvas.width)
    x = canvas.width - across - 3
    crown = _crown_tree(block)
    shape = _shape(crown, x - 6, canvas.height - _TRUNK - 2)
    tall = shape.top + round(shape.ry) + _TRUNK + 2  # crown, trunk and sign
    ax, ay = 3 + (x - 6) / 2, max(2, (canvas.height - tall) // 2) + shape.top
    canvas.target = (block.digit,)
    bottom = trees.draw(canvas, crown, shape, ax, ay, phase, hits or ())
    _trunk_and_sign(canvas, block, shape, ax, bottom, min(canvas.height - 3, bottom + _TRUNK))
    canvas.target = ()
    letters = tuple(arrangement.trees[(block.name, t.key)].letter for t in block.trees)
    most = canvas.height - 6
    lemon_list.draw(
        canvas,
        x,
        2,
        crown,
        "",
        block.color,
        phase,
        hits,
        bool(opened),
        most,
        edited,
        flipped,
        width=across,
        row_keys=letters,
    )
    shown = len(block.trees) if len(block.trees) <= most else most - 1
    drawn = {}
    for i, (tree, letter) in enumerate(zip(block.trees[:shown], letters, strict=False)):
        _claim(canvas, x + 1, 3 + i, across - 2, (block.digit, letter))
        drawn[tree.key] = (x, 3 + i, across, 1)
    return drawn
