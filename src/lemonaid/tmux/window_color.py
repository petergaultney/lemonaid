"""Deterministic color formatting for tmux window/tab titles.

Generates tmux-format colored output based on directory names,
using a hash to pick from a color palette for visual distinction.
"""

import os
import re
import sys

COLORS = [
    "#FF5555",  # Bright Red
    "#50FA7B",  # Bright Green
    "#F1FA8C",  # Bright Yellow
    "#A66BE0",  # Bright Purple
    "#FF79C6",  # Bright Pink
    "#8BE9FD",  # Bright Cyan
    "#FFB86C",  # Bright Orange
    "#9AEDFE",  # Light Blue
    "#5AF78E",  # Light Green
    "#F4F99D",  # Light Yellow
    "#CAA9FA",  # Light Purple
    "#FF6E67",  # Light Red
    "#ADEDC8",  # Soft Green
    "#FEA44D",  # Soft Orange
    "#F07178",  # Coral
    "#00B1B3",  # Teal
    "#E6DB74",  # Muted Yellow
    "#7DCFFF",  # Sky Blue
    "#D8A0DF",  # Lavender
    "#36C2C2",  # Aqua
    "#FF9E64",  # Peach
    "#85DACC",  # Mint
    "#E3CF65",  # Gold
]

# Special overrides for known directory names
DIR_COLORS: dict[str, str] = {
    "apps": "#00FFFF",  # Cyan
    "libs": "#F1FA8C",  # Yellow
    "mops": "#50FA7B",  # Green
}

# Special colors for known processes
PROCESS_COLORS: dict[str, str] = {
    "emacs": "#FFB86C",  # Orange
    "emacsclient": "#FFB86C",
    "git": "#BB55FF",  # Purple
    "python": "#F1FA8C",  # Yellow
    "python3": "#F1FA8C",
    "node": "#50FA7B",  # Green
    "npm": "#50FA7B",
    "claude": "#E3CF65",  # Gold
}

# Shells/wrappers that shouldn't be shown (just show directory instead)
HIDDEN_PROCESSES: set[str] = {
    "xonsh",
    "bash",
    "zsh",
    "fish",
    "sh",
    "starship",
    "mise",
}

# Interpreters where we prefer pane_title over the interpreter name
INTERPRETER_PROCESSES: set[str] = {
    "python",
    "python3",
    "python3.10",
    "python3.11",
    "python3.12",
    "python3.13",
    "node",
    "ruby",
    "perl",
}


def djb2(s: str) -> int:
    """DJB2 hash algorithm for deterministic string hashing."""
    h = 5381
    for c in s:
        h = ((h * 33) + ord(c)) & 0xFFFFFFFF
    return h


def get_color(name: str) -> str:
    """Get a deterministic color for a directory/file name."""
    return DIR_COLORS.get(name, COLORS[djb2(name) % len(COLORS)])


def format_path(path: str) -> str:
    """Format a path with tmux color codes.

    Args:
        path: A filesystem path (can be file:// URL or regular path)

    Returns:
        Tmux-formatted string with color codes like #[fg=#FF5555]
    """
    # Normalize: strip file:// prefix
    if path.startswith("file://"):
        path = path[7:]

    # Replace $HOME with ~
    home = os.environ.get("HOME", "")
    if home and path.startswith(home):
        path = "~" + path[len(home) :]

    # Get path components
    parts = [p for p in path.split("/") if p]

    # Determine display parts (last two components, like WezTerm)
    if len(parts) >= 2:
        display_parts = ["~", parts[-1]] if parts[-2] == "~" else parts[-2:]
    elif parts:
        display_parts = parts
    else:
        return "/"

    # Format with tmux colors
    result = []
    for i, part in enumerate(display_parts):
        if i > 0:
            result.append("/")
        color = get_color(part)
        result.append(f"#[fg={color}]{part}#[fg=default]")

    return "".join(result)


def extract_app_from_title(title: str | None, path: str) -> str | None:
    """Extract a meaningful app name from the pane title.

    Many shells/prompts set titles like "app - hostname" or "app user@host path".
    We try to extract just the app name from the beginning.

    Returns None if no meaningful app name found.
    """
    if not title or not title.strip():
        return None

    # Get the first word/token from the title
    title = title.strip()
    first_word = title.split()[0] if title.split() else ""

    if not first_word:
        return None

    # Skip if it looks like a path
    if first_word.startswith("/") or first_word.startswith("~"):
        return None

    # Skip if it looks like a hostname or user@host
    if "@" in first_word:
        return None

    # Skip if it matches common shell defaults
    if first_word in {"bash", "zsh", "fish", "xonsh", "-bash", "-zsh", "sh"}:
        return None

    # Skip if it's the same as the last path component (common default)
    path_parts = [p for p in path.split("/") if p]
    if path_parts and first_word == path_parts[-1]:
        return None

    return first_word


def format_process(process: str) -> str | None:
    """Format a process name with tmux color codes.

    Returns None if the process should be hidden (shells, wrappers).
    """
    if not process or process in HIDDEN_PROCESSES:
        return None

    # Version strings like "2.1.11" are likely Claude Code
    if re.match(r"^\d+\.\d+\.\d+$", process):
        process = "claude"

    color = PROCESS_COLORS.get(process, get_color(process))
    return f"#[fg={color}]{process}#[fg=default]"


def format_window(path: str, process: str | None = None, title: str | None = None) -> str:
    """Format a window title with optional process and path.

    Args:
        path: The current working directory
        process: The foreground process name (optional)
        title: The pane title, if set by the application (optional)

    Returns:
        Formatted string like "git: play/lemonaid" or just "play/lemonaid"
    """
    formatted_path = format_path(path)

    # If we have a meaningful title and process is an interpreter, prefer title
    if process in INTERPRETER_PROCESSES:
        app_name = extract_app_from_title(title, path)
        if app_name:
            process = app_name

    formatted_process = format_process(process) if process else None

    if formatted_process:
        return f"{formatted_process}: {formatted_path}"
    return formatted_path


def main() -> None:
    """CLI entry point for direct script execution.

    Usage: tmux-window-color <path> [process] [title]
    """
    if len(sys.argv) > 1:
        path = sys.argv[1]
        process = sys.argv[2] if len(sys.argv) > 2 else None
        title = sys.argv[3] if len(sys.argv) > 3 else None
        print(format_window(path, process, title))
    else:
        print("Usage: tmux-window-color <path> [process] [title]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
