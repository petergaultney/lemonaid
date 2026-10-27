"""Where the Codex session a hook fires for is running: its tty and tmux pane."""

import os
from typing import Any

from ..lemon_watchers import (
    get_cmux_surface,
    get_tmux_pane_tty,
    get_tmux_session_name,
    get_tmux_session_order,
    get_tmux_socket,
    get_tmux_window_index,
    get_tty,
)
from . import hosting


def pane_metadata(switch_source: str) -> dict[str, Any]:
    """The hook's tty and tmux identity, as inbox row metadata; {} under the app-server daemon.

    Under the daemon, the tty found is the daemon's, not this session's pane;
    recording it would put every Codex session in one pane. Otherwise the hook
    runs in the session's own pane, and the tmux session identity keeps a later
    TTY reuse from making another Codex session look like this one.
    """
    if hosting.under_app_server():
        return {}

    tty = get_tty() or (get_tmux_pane_tty() if switch_source == "tmux" else None)
    if not tty:
        return {}

    metadata: dict[str, Any] = {"tty": tty}
    if surface := get_cmux_surface():
        metadata["cmux_surface"] = surface
    if switch_source != "tmux":
        return metadata

    if tmux_session := get_tmux_session_name():
        metadata["tmux_session"] = tmux_session
    if window := get_tmux_window_index():
        metadata["tmux_window"] = window
    if socket := get_tmux_socket():
        metadata["tmux_socket"] = socket
    if session_order := get_tmux_session_order():
        metadata["tmux_session_order"] = list(session_order)
        if pane := os.environ.get("TMUX_PANE"):
            metadata["tmux_pane_identity"] = [pane, session_order[1]]
    return metadata
