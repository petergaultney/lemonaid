"""The packhouse: the lemons in no group, drawn as bays in a building at the grove's middle."""

from collections import abc

from ..layout.arrange import Arrangement
from ..model import Block, Tree
from . import colors, lemon_list
from .canvas import BACKGROUND, DOUBLE, Canvas, box, fill, mix, put, text, wide
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
    key = f" {block.digit}{letter} "
    if status in colors.STATUS:
        text(canvas, x, y, key, colors.on_status(status), colors.STATUS[status], bold=True)
    else:  # as a tree's tag draws its key cap without a status
        text(canvas, x, y, key, colors.TAG, colors.TEXT, bold=True)
    dots = len(tree.lemons) * 2
    main = tree.lemons[0]
    if main.pinned:
        put(canvas, x - 1, y, "▐", colors.TEXT, _FLOOR)
    shift = 3 if main.emoji else 0
    if main.emoji:
        wide(canvas, x + len(key) + 1, y, main.emoji, colors.TEXT, _FLOOR)
    text(
        canvas,
        x + len(key) + 1 + shift,
        y,
        label,
        colors.TEXT,
        _FLOOR,
        bold=True,
        limit=width - 7 - dots - shift,
    )
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


def _rows(block: Block, arrangement: Arrangement, room: int) -> list[tuple[Tree, int]]:
    """Each drawn session and its line within `room` lines, in bay order.

    Sessions sit at their saved bays, two lines apart, while all of them fit that way. Otherwise
    they pack onto the lines of the sessions that exist, a blank line apart if that fits and
    one per line if not; when even that is too many, the last line is left for a count of the rest.
    """
    trees = sorted(block.trees, key=lambda t: arrangement.trees[(block.name, t.key)].bay)
    if all(arrangement.trees[(block.name, t.key)].bay * 2 < room for t in trees):
        return [(t, arrangement.trees[(block.name, t.key)].bay * 2) for t in trees]

    if len(trees) * 2 - 1 <= room:
        return [(t, i * 2) for i, t in enumerate(trees)]

    if len(trees) <= room:
        return list(zip(trees, range(room)))

    return list(zip(trees[: room - 1], range(room - 1)))


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
    for tree, row in _rows(block, arrangement, h - 3):
        canvas.dim = fade(tree)
        standing = arrangement.trees[(block.name, tree.key)]
        _bay(canvas, block, tree, standing.letter, standing.label, x0 + 2, y0 + 2 + row, w - 4, phase)
        canvas.dim = 0.0
    shown = len(_rows(block, arrangement, h - 3))
    if shown < len(block.trees):
        more = f"+{len(block.trees) - shown} more"
        text(canvas, x0 + 2, y0 + h - 2, more, colors.TEXT, _FLOOR)
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
    key_prefix: str = "",
) -> dict[str, tuple[int, int, int, int]]:
    """The packhouse filling the screen, each session's lemons listed in its own bay; returns
    where each session's list went.
    """
    x0, y0, w, h = 3, 2, canvas.width - 6, canvas.height - 4
    canvas.target = (block.digit,)
    fill(canvas, x0, y0 + 1, w, h - 1, _FLOOR)
    box(canvas, x0, y0 + 1, w, h - 1, mix(block.color, BACKGROUND, 0.3), DOUBLE)
    for col in range(x0 - 1, x0 + w + 1):
        put(canvas, col, y0, "▄", _ROOF)
    sign = f" {block.digit} PACKHOUSE "
    text(canvas, x0 + (w - len(sign)) // 2, y0, sign, "#0b0e13", block.color, bold=True)
    canvas.target = ()
    across = lemon_list.width(canvas.width)
    columns = max(1, (w - 4) // (across + 2))
    # Rows for every bay the layout has saved, gone ones included, so a session leaving moves
    # no other bay; the count rises only when the packhouse holds more sessions than ever before.
    rows = arrangement.bays.get(block.name, 0) // columns + 1
    # Fewer lemons a bay when they don't all fit, so every bay stays on screen.
    lemons = max(2, min(_BAY_LEMONS, (h - 4) // rows - 3))  # 2: a key, then how many more
    drawn = {}
    for tree in block.trees:
        row, column = divmod(arrangement.trees[(block.name, tree.key)].bay, columns)
        letter = arrangement.trees[(block.name, tree.key)].letter
        x, y = x0 + 2 + column * (across + 2), y0 + 3 + row * (lemons + 3)
        drawn[tree.key] = (x, y, across, min(len(tree.lemons), lemons) + 2)
        canvas.target = (block.digit, letter)
        lemon_list.draw(
            canvas,
            x,
            y,
            tree,
            letter,
            block.color,
            phase,
            hits,
            letter == opened,
            lemons,
            edited,
            flipped,
            key_prefix + letter if key_prefix else "",
            across,
        )
        canvas.target = ()
    return drawn
