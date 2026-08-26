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

# Fields that stay plain even when a row is demanding attention.
_NEVER_BOLD = frozenset({"message"})

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

    The message is never bold. It is the one field that reads as prose rather
    than as a value to pick out, and a wrapped bold paragraph is harder to read
    than the plain one beside it - the weight costs more than the emphasis buys.
    """
    style = (HISTORY_FIELD_STYLES if history else FIELD_STYLES).get(field, "default")
    if is_unread and field not in _NEVER_BOLD:
        return Text(value, style=f"bold {style}")

    return Text(value, style=style)


# Ten rows get a digit; 1-9 then 0, so the key's position on the keyboard runs
# in the same direction as the list. Past that you scroll: a second digit would
# need a timeout to tell "1" from "12", and the wait would be felt on every jump.
JUMP_DIGITS = "1234567890"
JUMP_GUTTER_STYLE = "bright_black"


def jump_digit(row_index: int) -> str:
    """The digit that jumps to `row_index`, or "" past the tenth row."""
    return JUMP_DIGITS[row_index] if row_index < len(JUMP_DIGITS) else ""


def jump_gutter(row_index: int) -> Text:
    """The number that prefixes a session's name, padded so names stay aligned."""
    digit = jump_digit(row_index)
    return Text(f"{digit} " if digit else "  ", style=JUMP_GUTTER_STYLE)
