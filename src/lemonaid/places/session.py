"""Inspect a named tmux session before a session-only toss."""

import subprocess

from . import ownership


def _exists(name: str) -> bool:
    try:
        found = subprocess.run(
            ["tmux", "has-session", "-t", f"={name}"], capture_output=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return False

    return found.returncode == 0


def inspect(
    name: str, known: list[ownership.Place]
) -> tuple[dict[str, list[ownership.Pane]] | None, str]:
    """Return all session windows, refusing one that occupies a managed place."""
    if not _exists(name):
        return (
            None,
            f"No configured root has a directory for {name!r}, and no tmux session has that name",
        )

    snapshot = ownership.pane_snapshot()
    if snapshot is None:
        return None, f"Could not inspect panes in session {name!r}; nothing was closed"

    panes = [pane for pane in snapshot if pane.session == name]
    if any(pane.path is None for pane in panes):
        return None, f"Session {name!r} has a pane with an unknown directory; nothing was closed"

    held = {
        place.key
        for pane in panes
        if pane.path is not None
        for place in [ownership.place_at(pane.path, known)]
        if place is not None
    }
    if held:
        return None, (
            f"Session {name!r} contains managed place(s) {', '.join(repr(key) for key in sorted(held))}. "
            "Toss those places by key instead."
        )

    windows: dict[str, list[ownership.Pane]] = {}
    for pane in panes:
        windows.setdefault(pane.window, []).append(pane)

    return windows, ""
