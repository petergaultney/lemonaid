"""TUI utilities and helpers."""

import sys

from rich.text import Text


def set_terminal_title(title: str) -> None:
    """Set the terminal/pane title via OSC escape sequence."""
    # OSC 0 sets both icon name and window title
    sys.stdout.write(f"\033]0;{title}\007")
    sys.stdout.flush()


def styled_cell(value: str, is_unread: bool) -> Text:
    """Style a cell value based on read/unread status."""
    if is_unread:
        return Text(value, style="bold cyan")

    return Text(value, style="dim")
