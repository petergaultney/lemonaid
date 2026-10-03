"""Closing the windows a toss planned, and nothing else.

A window that closes on its own leaves its session running, so the clients
looking at it are moved to a sibling window rather than out of the session. Not
knowing who is looking is treated like a client with nowhere to go: the close
is refused.
"""

import os
import subprocess
from collections import abc

from ..log import get_logger
from . import ownership

_log = get_logger("places.windows")

_TIMEOUT_SECONDS = 5

Planned = abc.Mapping[str, abc.Sequence[ownership.Pane]]  # window ID -> its panes when planned


def _tmux(*args: str) -> list[str] | None:
    """Non-empty lines from a tmux query, or None when tmux did not answer."""
    try:
        result = subprocess.run(
            ["tmux", *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("tmux %s failed: %s", args[0], e)
        return None

    return [line for line in result.stdout.splitlines() if line]


def _survivor(session: str, doomed: abc.Container[str]) -> str:
    listed = _tmux("list-windows", "-t", f"={session}", "-F", "#{window_id}") or []

    return next((w for w in listed if w not in doomed), "")


def move_clients_off(doomed: abc.Collection[str]) -> str:
    """Point each client looking at a doomed window at another window of its session.

    The session survives, so this is a window change rather than a session
    change: the client stays where it is and sees the doomed window vanish from
    under it. Returns an error message, or "".
    """
    listed = _tmux("list-clients", "-F", "#{client_name}\t#{client_session}\t#{window_id}")
    if listed is None:
        return "Could not tell who is looking at the closing windows; nothing was closed."

    for client, session, window in (line.split("\t") for line in listed):
        if window not in doomed:
            continue

        target = _survivor(session, doomed)
        if not target:
            return f"Nowhere in '{session}' to move {client} to; nothing was closed."

        try:
            subprocess.run(
                ["tmux", "switch-client", "-c", client, "-t", target],
                check=True,
                capture_output=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as e:
            return f"Could not move {client} off {window}: {e}; nothing was closed."

    return ""


def own_window() -> str:
    """The window this process runs in, or "" outside tmux.

    Closing it would end this process, so the caller leaves it for the reaper.
    """
    pane = os.environ.get("TMUX_PANE", "")
    if not pane:
        return ""

    return next(iter(_tmux("display-message", "-p", "-t", pane, "#{window_id}") or []), "")


def ttys(windows: abc.Iterable[str]) -> set[str]:
    """The ttys of every pane in *windows*."""
    return {
        tty
        for window in windows
        for tty in _tmux("list-panes", "-t", window, "-F", "#{pane_tty}") or []
    }


def close(windows: abc.Iterable[str]) -> list[str]:
    """Kill each window, returning the IDs that would not die."""
    failed = []
    for window in windows:
        try:
            subprocess.run(
                ["tmux", "kill-window", "-t", window],
                check=True,
                capture_output=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as e:
            _log.warning("could not close window %s: %s", window, e)
            failed.append(window)

    return failed
