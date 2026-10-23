"""The list of a tree's lemons drawn beside it when its block is zoomed in."""

from collections.abc import Container

from ..model import Tree
from . import colors
from .canvas import BACKGROUND, DOUBLE, ROUND, Canvas, box, fill, mix, put, text, wide

WIDTH = 60
# Where each column starts, and how wide it may run, with a blank cell between columns.
_KEY, _GLYPH, _EMOJI = 1, 5, 7
_NAME, _NAME_WIDTH = 10, 15
_DETAIL, _DETAIL_WIDTH = 26, 16
_MODEL, _MODEL_WIDTH = 43, 10
_CONTEXT_END = 57  # right-aligned, up to four cells
_PIN = 58
_PANEL = "#121821"


def key(tree: Tree, letter: str, index: int) -> str:
    """What to type, after the block's digit, to reach lemon *index* of *tree*."""
    if len(tree.lemons) >= 3:
        return f"{letter}{index + 1}"

    return letter if index == 0 else letter.upper()


def _row(canvas: Canvas, x: int, y: int, tree: Tree, letter: str, i: int, phase: float) -> None:
    lemon = tree.lemons[i]
    keys = key(tree, letter, i)
    text(
        canvas,
        x + _KEY + 3 - len(keys),
        y,
        keys,
        colors.status_text(lemon.status) if lemon.status else colors.TEXT,
        _PANEL,
        bold=True,
        underline=True,
    )
    put(
        canvas,
        x + _GLYPH,
        y,
        colors.lemon_glyph(lemon),
        colors.lemon_color(lemon, phase),
        _PANEL,
        bold=True,
    )
    if lemon.emoji:
        wide(canvas, x + _EMOJI, y, lemon.emoji, colors.TEXT, _PANEL)
    name_color = colors.IDLE if lemon.quiet else colors.TEXT
    text(
        canvas,
        x + _NAME,
        y,
        lemon.brief_id or lemon.name,
        name_color,
        _PANEL,
        bold=True,
        limit=_NAME_WIDTH,
    )
    detail = lemon.status or lemon.name.replace("REVIEW ", "review ")
    detail_color = colors.status_text(lemon.status) if lemon.status else colors.MUTED
    text(
        canvas,
        x + _DETAIL,
        y,
        detail,
        detail_color,
        _PANEL,
        bold=bool(lemon.status),
        limit=_DETAIL_WIDTH,
    )
    text(canvas, x + _MODEL, y, lemon.model, colors.MUTED, _PANEL, limit=_MODEL_WIDTH)
    context = lemon.context[-4:]
    text(canvas, x + _CONTEXT_END + 1 - len(context), y, context, colors.IDLE, _PANEL)
    if lemon.pinned:
        put(canvas, x + _PIN, y, "▪", colors.TEXT, _PANEL)


def draw(
    canvas: Canvas,
    x: int,
    y: int,
    tree: Tree,
    letter: str,
    color: str,
    phase: float,
    hits: Container[str] | None,
    opened: bool,
    most: int = 0,
) -> None:
    """*most*, when given, lists that many rows at most, the last saying how many more there are."""
    shown = len(tree.lemons) if not most or len(tree.lemons) <= most else most - 1
    height = min(len(tree.lemons), most or len(tree.lemons)) + 2
    fill(canvas, x, y, WIDTH, height, _PANEL)
    box(
        canvas,
        x,
        y,
        WIDTH,
        height,
        colors.LEMON if opened else mix(color, BACKGROUND, 0.5),
        DOUBLE if opened else ROUND,
    )
    title = f" {tree.key} "
    text(canvas, x + 2, y, title, "#9aa5b8", _PANEL, limit=WIDTH - 4)
    dim = canvas.dim
    for i, lemon in enumerate(tree.lemons[:shown]):
        row = y + 1 + i
        canvas.dim = 0.6 if hits is not None and lemon.channel not in hits else dim
        _row(canvas, x, row, tree, letter, i, phase)
    canvas.dim = dim
    if shown < len(tree.lemons):
        text(
            canvas,
            x + _NAME,
            y + 1 + shown,
            f"+{len(tree.lemons) - shown} more",
            colors.MUTED,
            _PANEL,
        )
