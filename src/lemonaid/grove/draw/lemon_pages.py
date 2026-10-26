"""The two pages of a row in a lemon list: its name, and where it is and when it reported.

Each draws from the row's text column to a cell short of the list's right border, *width*
cells from its left; any width past the narrowest goes to the name.
"""

from pathlib import PurePath

from ..model import Lemon
from . import colors
from .canvas import Canvas, text

TEXT = 10  # where a row's text starts, after its key, dot and emoji
# The WordyBin's column, and on the other page the model's, as long as `Sonnet 5.5`, counted
# from the list's right edge
_WHO, _WHO_WIDTH = 16, 10
_LAST_END = 3  # from the right edge, right-aligned, up to four cells: the age, or the context
# Statuses that ask something of the user, which the name page names as well as colors.
_ASKING = ("blocked", "alert", "merge", "approve")


def _age(canvas: Canvas, end: int, y: int, lemon: Lemon, panel: str) -> None:
    age = "now" if lemon.age == "just now" else lemon.age.removesuffix(" ago")
    text(canvas, end + 1 - len(age), y, age, colors.IDLE, panel)


def _context(canvas: Canvas, end: int, y: int, lemon: Lemon, panel: str) -> None:
    context = lemon.context[-4:]
    text(canvas, end + 1 - len(context), y, context, colors.reading_color(context), panel)


def name_first(canvas: Canvas, x: int, y: int, lemon: Lemon, panel: str, width: int) -> None:
    who = width - _WHO
    tag = lemon.status if lemon.status in _ASKING else ""
    if tag:
        text(
            canvas,
            x + who - 1 - len(tag),
            y,
            tag,
            colors.status_text(tag),
            panel,
            bold=True,
        )
    text(
        canvas,
        x + TEXT,
        y,
        lemon.name,
        colors.IDLE if lemon.quiet else colors.TEXT,
        panel,
        bold=True,
        limit=who - 1 - TEXT - (len(tag) + 1 if tag else 0),
    )
    text(canvas, x + who, y, lemon.brief_id, colors.MUTED, panel, limit=_WHO_WIDTH)
    _age(canvas, x + width - _LAST_END, y, lemon, panel)


def where_and_when(canvas: Canvas, x: int, y: int, lemon: Lemon, panel: str, width: int) -> None:
    """PR numbers and branch as the inbox shows them: numbers bold and linked, branch magenta."""
    at, end = x + TEXT, x + width - _WHO - 1
    for number, url in lemon.prs:
        text(canvas, at, y, f"#{number}", colors.TEXT, panel, bold=True, limit=end - at, link=url)
        at += len(number) + 2
    text(
        canvas,
        at,
        y,
        # without its project, `garden/`, which the list's title usually names
        lemon.branch.rpartition("/")[2] or PurePath(lemon.cwd).name,
        colors.BRANCH,
        panel,
        limit=end - at,
    )
    text(
        canvas, x + width - _WHO, y, lemon.model, colors.model_color(lemon), panel, limit=_WHO_WIDTH
    )
    _context(canvas, x + width - _LAST_END, y, lemon, panel)
