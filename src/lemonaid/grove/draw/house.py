"""The packhouse: the lemons in no group, drawn as bays in a building at the grove's middle."""

from collections import abc

from ..layout.arrange import Arrangement
from ..model import Block, Tree
from . import colors, lemon_list
from .canvas import BACKGROUND, DOUBLE, Canvas, box, fill, mix, put, text
from .plots import View

_FLOOR = "#1d1f24"
_ROOF = "#7a3b2e"
# Lemons a zoomed bay lists before saying how many more, so every row of bays is the same
# height and no bay moves as sessions come, go or grow; fewer when the screen can't fit them.
_BAY_LEMONS = 5


def _bay(
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
    canvas.target = (block.digit, letter)
    status = colors.tree_status(tree.lemons)
    cap = colors.STATUS.get(status, mix(block.color, BACKGROUND, 0.2))
    key = f" {block.digit}{letter} "
    text(canvas, x, y, key, colors.on_status(status) if status else "#0b0e13", cap, bold=True)
    dots = len(tree.lemons) * 2
    text(canvas, x + len(key) + 1, y, label, colors.TEXT, _FLOOR, bold=True, limit=width - 7 - dots)
    for i, lemon in enumerate(tree.lemons):
        put(
            canvas,
            x + width - dots + 2 * i,
            y,
            colors.lemon_glyph(lemon),
            colors.lemon_color(lemon, phase),
            _FLOOR,
            bold=True,
        )
    canvas.target = ()


def draw(
    canvas: Canvas,
    block: Block,
    arrangement: Arrangement,
    view: View,
    phase: float,
    fade: abc.Callable[[Tree], float],
) -> tuple[int, int, int, int]:
    """Draw the packhouse; return where it is, roof included, (x, y, w, h)."""
    plot = arrangement.plots[block.name]
    x0, y0 = (round(v) for v in view.screen(plot.x, plot.y))
    x1, y1 = (round(v) for v in view.screen(plot.x + plot.w, plot.y + plot.h))
    w, h = max(12, x1 - x0), max(5, y1 - y0)
    canvas.target = (block.digit,)
    fill(canvas, x0, y0 + 1, w, h - 1, _FLOOR)
    box(canvas, x0, y0 + 1, w, h - 1, mix(block.color, BACKGROUND, 0.3), DOUBLE)
    for col in range(x0 - 1, x0 + w + 1):
        put(canvas, col, y0, "▄", _ROOF)
    sign = f" {block.digit} PACKHOUSE "
    text(canvas, x0 + (w - len(sign)) // 2, y0, sign, "#0b0e13", block.color, bold=True)
    canvas.target = ()
    room = h - 3
    for tree in block.trees:
        i = arrangement.trees[(block.name, tree.key)].bay
        if i * 2 > room:
            continue  # beyond what the drawing has room for; zoomed in, every bay shows

        canvas.dim = fade(tree)
        standing = arrangement.trees[(block.name, tree.key)]
        _bay(
            canvas,
            block,
            tree,
            standing.letter,
            standing.label,
            x0 + 2,
            y0 + 2 + i * 2,
            w - 4,
            phase,
        )
        canvas.dim = 0.0
    return x0 - 1, y0, w + 2, h


def zoomed(
    canvas: Canvas,
    block: Block,
    arrangement: Arrangement,
    phase: float,
    hits: abc.Container[str] | None,
    opened: str,
    edited: str = "",
    flipped: bool = False,
) -> None:
    """The packhouse filling the screen, each session's lemons listed in its own bay."""
    x0, y0, w, h = 3, 2, canvas.width - 6, canvas.height - 4
    canvas.target = (block.digit,)
    fill(canvas, x0, y0 + 1, w, h - 1, _FLOOR)
    box(canvas, x0, y0 + 1, w, h - 1, mix(block.color, BACKGROUND, 0.3), DOUBLE)
    for col in range(x0 - 1, x0 + w + 1):
        put(canvas, col, y0, "▄", _ROOF)
    sign = f" {block.digit} PACKHOUSE "
    text(canvas, x0 + (w - len(sign)) // 2, y0, sign, "#0b0e13", block.color, bold=True)
    canvas.target = ()
    columns = max(1, (w - 4) // (lemon_list.WIDTH + 2))
    # Rows for every bay the layout has saved, gone ones included, so a session leaving moves
    # no other bay; the count rises only when the packhouse holds more sessions than ever before.
    rows = arrangement.bays.get(block.name, 0) // columns + 1
    # Fewer lemons a bay when they don't all fit, so every bay stays on screen.
    lemons = max(2, min(_BAY_LEMONS, (h - 4) // rows - 3))  # 2: a key, then how many more
    for tree in block.trees:
        row, column = divmod(arrangement.trees[(block.name, tree.key)].bay, columns)
        letter = arrangement.trees[(block.name, tree.key)].letter
        canvas.target = (block.digit, letter)
        lemon_list.draw(
            canvas,
            x0 + 2 + column * (lemon_list.WIDTH + 2),
            y0 + 3 + row * (lemons + 3),
            tree,
            letter,
            block.color,
            phase,
            hits,
            letter == opened,
            lemons,
            edited,
            flipped,
        )
        canvas.target = ()
