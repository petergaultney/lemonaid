"""Each window's tab label, as `window_status` formats it, for the label client to store.

A window's label depends only on its active pane's paths, command, title and pid, so the
client lists those for every window and relabels a window only when they change.
"""

import typing as ty
from collections import abc

from .. import window_status

SUBSCRIPTION = "lemonaid-labels"
LABEL = "@lemonaid_label"
CURRENT_LABEL = "@lemonaid_label_current"  # the active window's variant

# Changes whenever any window's label inputs do; only its changing matters.
CHANGES = (
    "#{S:#{W:#{window_id}|#{pane_path}|#{pane_current_path}|#{pane_current_command}"
    "|#{pane_pid}|#{pane_title};}}"
)
# Tab-separated, the title last because it may hold tabs.
FIELDS = (
    "#{window_id}\t#{pane_path}\t#{pane_current_path}\t#{pane_current_command}"
    "\t#{pane_pid}\t#{pane_title}"
)


class Window(ty.NamedTuple):
    window_id: str
    pane_path: str
    pane_current_path: str
    command: str
    pane_pid: str
    title: str


def parse(line: str) -> Window | None:
    parts = line.split("\t", 5)
    return Window(*parts) if len(parts) == 6 and parts[0].startswith("@") else None


def labels(window: Window, named_processes: abc.Collection[str]) -> tuple[str, str]:
    """The label for a window that isn't current, and for one that is."""

    def label(active: bool) -> str:
        return window_status.format_window(
            window.pane_path or window.pane_current_path,
            window.command or None,
            window.title or None,
            active,
            window.pane_pid or None,
            named_processes=named_processes,
        )

    return label(False), label(True)


def quoted(value: str) -> str:
    """A tmux command argument that reads back as *value*; tmux parses quotes as a shell does."""
    return "'" + value.replace("'", "'\\''") + "'"


def set_commands(window_id: str, inactive: str, active: str) -> tuple[str, str]:
    """One command each, since a control client gets one response per command."""
    return (
        f"set-option -w -t {window_id} {LABEL} {quoted(inactive)}",
        f"set-option -w -t {window_id} {CURRENT_LABEL} {quoted(active)}",
    )
