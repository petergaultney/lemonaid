"""Closing an ended lemon's own pane, and nothing else.

Only a pane its harness has left, with nothing or its starting shell still in it, is
closed. A window closes with its last pane, but a session's last pane stays: ending a
session is what `place toss` is for.
"""

import collections
import subprocess
import time
from collections import abc

from ..restart import pane

_SETTLE_SECONDS = 5.0  # for the harness's tools to leave the terminal after it exits


def _layout(target: pane.Pane) -> tuple[str, dict[str, list[str]]]:
    """*target*'s session, and the panes of each of its windows."""
    session = pane.run(target.socket, "display-message", "-p", "-t", target.pane, "#{session_name}")
    rows = pane.run(
        target.socket, "list-panes", "-s", "-t", f"={session}", "-F", "#{window_id}\t#{pane_id}"
    )
    windows = collections.defaultdict(list)
    for line in rows.splitlines():
        window, _, found = line.partition("\t")
        windows[window].append(found)
    return session, dict(windows)


def _kept(target: pane.Pane, protected: abc.Collection[str]) -> str:
    """Why *target* stays open whatever runs in it, or ""."""
    session, windows = _layout(target)
    if session in protected:
        return f"session {session!r} is protected"

    if [found for panes in windows.values() for found in panes] == [target.pane]:
        return f"it is the last pane of session {session!r}; `lemonaid place toss` ends a place"

    return ""


def _closed(target: pane.Pane) -> str:
    _, windows = _layout(target)
    alone = windows.get(target.window) == [target.pane]
    pane.run(target.socket, "kill-pane", "-t", target.pane)
    return f"closed its pane {target.pane}" + (
        f" and its window {target.window}" if alone else ", leaving the other panes in its window"
    )


def preview(target: pane.Pane, protected: abc.Collection[str]) -> str:
    """What `close` would do with *target*, before its harness stops."""
    try:
        if why := _kept(target, protected):
            return f"leave its pane {target.pane} open: {why}"

        _, windows = _layout(target)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        return f"leave its pane {target.pane} open: {error}"

    alone = windows.get(target.window) == [target.pane]
    return (
        f"close its pane {target.pane}{f' and its window {target.window}' if alone else ''}"
        ", once only its shell is left there"
    )


def close(target: pane.Pane, exit_option: str, protected: abc.Collection[str]) -> str:
    """Close *target*, whose harness has exited, unless something holds it open; what happened.

    A pane that stays open gets its `remain-on-exit` back as *exit_option*.
    """
    try:
        current = pane.check(target)
        if not (why := _kept(current, protected)):
            deadline = time.monotonic() + _SETTLE_SECONDS
            while not pane.only_shell(current):
                if time.monotonic() >= deadline:
                    why = "other jobs still run in it"
                    break

                time.sleep(0.1)
                current = pane.check(target)
        if not why:
            return _closed(current)

        pane.restore(current, exit_option)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        return f"left its pane {target.pane} open: {error}"

    return f"left its pane {target.pane} open: {why}"
