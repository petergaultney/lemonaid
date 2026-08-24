"""TUI utilities and helpers."""

import sys

from rich.text import Text


def set_terminal_title(title: str) -> None:
    """Set the terminal/pane title via OSC escape sequence."""
    # OSC 0 sets both icon name and window title
    sys.stdout.write(f"\033]0;{title}\007")
    sys.stdout.flush()


# What each field is, rather than what state its session is in. Colour carries the
# field's identity so the eye can find one without reading the others; read/unread
# is carried by weight and the marker, which leaves it free to say something else.
FIELD_STYLES = {
    "time": "green",
    "backend": "bright_black",
    "name": "cyan",
    "branch": "magenta",
    "cwd": "blue",
    "message": "default",
    "tty": "bright_black",
}
UNREAD_MARKER_STYLE = "bold bright_red"

# History is a record rather than a queue, so its timestamps are the settled
# kind. Green is the live colour and belongs to the inbox.
HISTORY_FIELD_STYLES = {**FIELD_STYLES, "time": "yellow"}


def styled_cell(
    value: str, is_unread: bool, field: str = "message", *, history: bool = False
) -> Text:
    """Colour a cell by which field it is, weighted by whether it wants attention.

    Read rows are plain rather than dim. Most of the inbox is read most of the
    time, and `dim` on a dark background costs enough contrast that the majority
    of the pane stops being readable - which is a high price for a distinction
    the bold unread rows already make on their own.
    """
    style = (HISTORY_FIELD_STYLES if history else FIELD_STYLES).get(field, "default")
    if is_unread:
        return Text(value, style=f"bold {style}")

    return Text(value, style=style)
