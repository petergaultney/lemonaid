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
    # A timestamp more than a day old, which reads as a date. Grey rather than
    # the live green: the column says "when" either way, and the colour says
    # whether it is still worth reacting to.
    "time_old": "bright_black",
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
HISTORY_FIELD_STYLES = {**FIELD_STYLES, "time": "yellow", "time_old": "bright_black"}


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

# The pane you are looking at right now, which tmux reports rather than the
# inbox remembering: a switch made outside lemonaid moves you just the same, and
# a remembered answer would be wrong until the next one made through it.
#
# A bar down the left edge rather than a glyph or a fill. It marks the row
# without tinting the text, which leaves the field colours and the row cursor's
# own background to say what they already say.
GUTTER_WIDTH = 2  # "<digit> ", or the bar and a space
# Two marks for the same thing, because the two layouts give it different room.
# A column row is one line tall, so it spends its single cell on a full block to
# be visible at that size. A card draws a thin rule instead, which reads as an
# edge over the height of the card where the heavier glyph would read as a slab.
HERE_BLOCK = "\u2588"
HERE_BAR = "\u2503"
HERE_BAR_STYLE = "bright_green"


def jump_digit(row_index: int) -> str:
    """The digit that jumps to `row_index`, or "" past the tenth row."""
    return JUMP_DIGITS[row_index] if row_index < len(JUMP_DIGITS) else ""


def jump_gutter(row_index: int, is_here: bool = False) -> Text:
    """The number that prefixes a session's name, padded so names stay aligned.

    The focused session takes the marker instead of its digit: it is the one row
    you have no reason to jump to, so the slot is free to say where you are.

    The style is a span rather than the Text's own: concatenating takes the left
    operand's base style for the whole result, so a background set here would
    run on under the name that follows it.
    """
    if is_here:
        gutter = Text(f"{HERE_BLOCK} ")
        gutter.stylize(HERE_BAR_STYLE, 0, len(HERE_BLOCK))
        return gutter

    digit = jump_digit(row_index)
    text = f"{digit} " if digit else "  "
    gutter = Text(text)
    gutter.stylize(JUMP_GUTTER_STYLE, 0, len(text))
    return gutter
