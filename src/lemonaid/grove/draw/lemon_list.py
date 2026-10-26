"""The list of a tree's lemons drawn beside it when its block is zoomed in."""

import string
from collections.abc import Container

from ..model import Tree
from . import colors, lemon_pages
from .canvas import BACKGROUND, DOUBLE, ROUND, Canvas, box, fill, mix, put, text, wide

WIDTH = 54  # the narrowest list, and a lemon card's width
_WIDEST = 72
# Where each column starts, and how wide it may run, with a blank cell between columns.
_KEY, _GLYPH, _EMOJI = 1, 5, 7
_PANEL = "#121821"
_EDITED = "#2c3e57"  # behind the row an edit would change


def width(screen: int) -> int:
    """How wide a list is on a screen *screen* columns wide: 30% of it, within its bounds."""
    return min(_WIDEST, max(WIDTH, round(screen * 0.3)))


def session(tree: Tree) -> str:
    """What marks *tree*'s session as an edit's target, where a lemon's channel marks a lemon: no
    channel starts with a colon.
    """
    return f":session:{tree.key}"


def lemon_number(index: int) -> str:
    """What picks lemon *index* after its tree's dotted letter: its place, `1` to `9`, then `0a`
    to `0z`, so no key waits to see whether another digit follows; "" past those, for a lemon
    reached only by search.
    """
    if 0 < index < 10:
        return str(index)
    if 10 <= index < 10 + len(string.ascii_lowercase):
        return f"0{string.ascii_lowercase[index - 10]}"
    return ""


def lemon_index(typed: str) -> int | None:
    if len(typed) == 1 and typed in "123456789":
        return int(typed)
    if len(typed) == 2 and typed[0] == "0" and typed[1] in string.ascii_lowercase:
        return 10 + string.ascii_lowercase.index(typed[1])
    return None


def key(tree: Tree, letter: str, index: int) -> str:
    """What to type, after the block's digit, to reach lemon *index* of *tree*: its tree's letter
    for the first, so a tree's main lemon keeps its key whatever joins it, and a dot, the letter
    and the lemon's place for the rest, as `.s1`.
    """
    if index == 0:
        return letter

    number = lemon_number(index)
    return f".{letter}{number}" if number else ""


def _row(
    canvas: Canvas,
    x: int,
    y: int,
    tree: Tree,
    letter: str,
    i: int,
    phase: float,
    panel: str,
    flipped: bool,
    width: int,
) -> None:
    lemon = tree.lemons[i]
    keys = key(tree, letter, i)
    text(
        canvas,
        x + _KEY + (i == 0),  # a lone letter under the letter of `.s1`
        y,
        keys,
        colors.status_text(lemon.status) if lemon.status else colors.TEXT,
        panel,
        bold=True,
        underline=True,
    )
    if lemon.unread or lemon.working:  # as the inbox's unread dot; a working one still pulses
        put(
            canvas,
            x + _GLYPH,
            y,
            colors.lemon_glyph(lemon),
            colors.lemon_color(lemon, phase),
            panel,
            bold=True,
        )
    if lemon.emoji:
        wide(canvas, x + _EMOJI, y, lemon.emoji, colors.TEXT, panel)
    (lemon_pages.where_and_when if flipped else lemon_pages.name_first)(
        canvas, x, y, lemon, panel, width
    )
    if lemon.pinned:
        put(canvas, x, y, "▐", colors.TEXT)


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
    edited: str = "",
    flipped: bool = False,
    title_key: str = "",
    width: int = WIDTH,
) -> None:
    """*most*, when given, lists that many rows at most, the last saying how many more there are.
    *edited* marks what an edit would change: a lemon's row, or the session, named in the title;
    a list cut short scrolls to keep an edited lemon in it. *flipped* lists each lemon's model,
    where it is and when it last reported in place of its name, WordyBin and context.
    *title_key*, when given, is a key named in the title before the tree, as select mode's `$l`.
    """
    shown = len(tree.lemons) if not most or len(tree.lemons) <= most else most - 1
    at = next((i for i, lemon in enumerate(tree.lemons) if lemon.channel == edited), 0)
    first = max(0, at - shown + 1)
    height = min(len(tree.lemons), most or len(tree.lemons)) + 2
    fill(canvas, x, y, width, height, _PANEL)
    box(
        canvas,
        x,
        y,
        width,
        height,
        colors.LEMON if opened else mix(color, BACKGROUND, 0.5),
        DOUBLE if opened else ROUND,
    )
    title = f" {title_key}  {tree.key} " if title_key else f" {tree.key} "
    if edited == session(tree):
        text(canvas, x + 2, y, title, BACKGROUND, colors.LEMON, bold=True, limit=width - 4)
    else:
        text(canvas, x + 2, y, title, "#9aa5b8", _PANEL, limit=width - 4)
    dim = canvas.dim
    for i, lemon in enumerate(tree.lemons[first : first + shown], start=first):
        row = y + 1 + i - first
        canvas.dim = 0.6 if hits is not None and lemon.channel not in hits else dim
        panel = _EDITED if lemon.channel == edited else _PANEL
        if panel != _PANEL:
            fill(canvas, x + 1, row, width - 2, 1, panel)
        _row(canvas, x, row, tree, letter, i, phase, panel, flipped, width)
    canvas.dim = dim
    if shown < len(tree.lemons):
        text(
            canvas,
            x + lemon_pages.TEXT,
            y + 1 + shown,
            f"+{len(tree.lemons) - shown} more",
            colors.MUTED,
            _PANEL,
        )
