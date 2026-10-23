"""The title row above the grove and the prompt row below it."""

from . import colors
from .canvas import Canvas, fill, put, text

_LEGEND = (
    ("alert", "alert"),
    ("blocked", "blocked"),
    ("running", "running"),
    ("merge", "merge"),
    ("review", "review"),
)


def title(canvas: Canvas, summary: str, keys: str) -> None:
    fill(canvas, 0, 0, canvas.width, 1, colors.BAR)
    text(canvas, 1, 0, " LEMON GROVE ", "#0b0e13", colors.LEMON, bold=True)
    text(canvas, 15, 0, summary, "#aab3c2", colors.BAR)
    text(canvas, canvas.width - len(keys) - 2, 0, keys, colors.MUTED, colors.BAR)


def prompt(canvas: Canvas, line: str, color: str = colors.TEXT) -> None:
    row = canvas.height - 1
    fill(canvas, 0, row, canvas.width, 1, colors.BAR)
    legend_width = sum(len(label) + 4 for _, label in _LEGEND) + len("idle") + 4
    room = canvas.width - legend_width - 4 if canvas.width > legend_width + 60 else canvas.width - 3
    text(canvas, 1, row, f"> {line}", color, colors.BAR, bold=True, limit=room)
    if room == canvas.width - 3:
        return

    x = canvas.width - legend_width
    for status, label in (*_LEGEND, ("", "idle")):
        put(canvas, x, row, "●", colors.STATUS.get(status, colors.IDLE), colors.BAR, bold=True)
        text(canvas, x + 2, row, label, colors.MUTED, colors.BAR)
        x += len(label) + 4
