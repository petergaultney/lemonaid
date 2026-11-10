"""The title row above the grove and the prompt row below it."""

from rich import color as rich_color
from rich.console import Console
from rich.text import Text

from ... import config, status_registry
from . import colors
from .canvas import BACKGROUND, Canvas, Cell, fill, mix, put, text

_CONSOLE = Console(color_system="truecolor")


def _legend() -> tuple[str, ...]:
    return tuple(s.name for s in config.brief_statuses() if s.name != status_registry.DONE)


def _hex(color: rich_color.Color | None, default: str) -> str:
    if color is None:
        return default

    return "#{:02x}{:02x}{:02x}".format(*color.get_truecolor())


def _chips(canvas: Canvas, x: int, chips: Text, limit: int) -> None:
    column = x
    for segment in chips.render(_CONSOLE):
        style = segment.style
        for char in segment.text:
            if column >= limit:
                return

            put(
                canvas,
                column,
                0,
                char,
                _hex(style.color if style else None, colors.MUTED),
                _hex(style.bgcolor if style else None, colors.BAR),
                bold=bool(style and style.bold),
            )
            column += 1


def title(canvas: Canvas, summary: str, keys: str, attention: Text) -> None:
    """The keys give way first, losing entries from the left, then the *attention* bar if it can't
    sit beside the *summary*."""
    fill(canvas, 0, 0, canvas.width, 1, colors.BAR)
    text(canvas, 1, 0, " LEMON GROVE ", "#0b0e13", colors.LEMON, bold=True)
    text(canvas, 15, 0, summary, "#aab3c2", colors.BAR)
    bar_at = 15 + len(summary) + 2
    bar_end = bar_at + attention.cell_len
    if bar_end <= canvas.width - 1:
        _chips(canvas, bar_at, attention, canvas.width - 1)
    else:
        bar_end = bar_at
    entries = keys.split(" · ")
    for shown in (" · ".join(entries[i:]) for i in range(len(entries))):
        if canvas.width - len(shown) - 2 >= bar_end + 2:
            text(canvas, canvas.width - len(shown) - 2, 0, shown, colors.MUTED, colors.BAR)
            return


def prompt(
    canvas: Canvas,
    line: str,
    color: str = colors.TEXT,
    key: str = "",
    key_color: str = "",
    label: str = "",
) -> None:
    row = canvas.height - 1
    fill(canvas, 0, row, canvas.width, 1, colors.BAR)
    legend = _legend()
    legend_width = sum(len(label) + 4 for label in legend) + len("idle") + 4 + len("no jump") + 4
    room = canvas.width - legend_width - 4 if canvas.width > legend_width + 60 else canvas.width - 3
    if key:
        text(canvas, 1, row, "> ", color, colors.BAR, bold=True, limit=room)
        text(canvas, 3, row, f" {key} ", "#0b0e13", key_color, bold=True, limit=room - 2)
        x = 6 + len(key)
        text(canvas, x, row, label, key_color, colors.BAR, bold=True, limit=room - x + 1)
        x += len(label) + 2
        text(canvas, x, row, line, color, colors.BAR, bold=True, limit=room - x + 1)
    else:
        text(canvas, 1, row, f"> {line}", color, colors.BAR, bold=True, limit=room)
    if room == canvas.width - 3:
        return

    x = canvas.width - legend_width
    for status, label in (*((s, s) for s in legend), ("", "idle"), ("", "no jump")):
        put(
            canvas,
            x,
            row,
            "x" if label == "no jump" else "●",
            colors.fill(status) or colors.IDLE,
            colors.BAR,
            bold=True,
        )
        text(canvas, x + 2, row, label, colors.MUTED, colors.BAR)
        x += len(label) + 4


_SELECT_BAR = "#3b3514"  # the title and prompt rows in select mode: the bar, tinted lemon


def select_frame(canvas: Canvas) -> None:
    """Select mode's frame: the screen's side columns in lemon, and its two bars tinted."""
    for row in canvas.rows[1:-1]:
        for cell in (row[0], row[-1]):
            cell.char, cell.bg, cell.target = " ", colors.LEMON, ()
    for row in (canvas.rows[0], canvas.rows[-1]):
        for cell in row:
            if cell.bg == colors.BAR:
                cell.bg = _SELECT_BAR


def tint(cell: Cell) -> None:
    """*cell* in alert red, for something that can't go where it is."""
    cell.bg = mix(cell.bg or BACKGROUND, colors.ALERT, 0.55)
    if "▀" <= cell.char <= "▟":  # a block glyph: a crown or trunk drawn in its fg
        cell.fg = mix(cell.fg, colors.ALERT, 0.55)


def flash(canvas: Canvas, target: tuple[str, ...]) -> None:
    """Every cell that reaches *target*, a tree with its tag and list, tinted alert red."""
    for row in canvas.rows:
        for cell in row:
            if cell.target == target:
                tint(cell)
