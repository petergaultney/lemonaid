"""Resolve saved tmux locations without following a reused tty."""

import subprocess
import typing as ty

from . import navigation


def has_identity(metadata: dict[str, ty.Any]) -> bool:
    return any(
        metadata.get(key) for key in ("tmux_session", "tmux_session_order", "tmux_pane_identity")
    )


def locate(metadata: dict[str, ty.Any]) -> tuple[str | None, str | None]:
    socket = metadata.get("tmux_socket")
    if socket and socket != navigation.current_socket():
        raise navigation.TmuxUnavailable("Recorded tmux server is not the current server")

    tty = metadata.get("tty")
    if not tty and not metadata.get("tmux_pane_identity"):
        return None, None

    if not has_identity(metadata):
        return navigation.get_pane_for_tty(tty)

    try:
        result = subprocess.run(
            [
                *navigation.server_args(socket),
                "list-panes",
                "-a",
                "-F",
                "#{pane_id}|#{pane_tty}|#{session_name}|#{session_created}|#{start_time}|#{session_id}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise navigation.TmuxUnavailable(str(error)) from error

    matches: set[tuple[str, str]] = set()
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) != 6 or (tty and parts[1] != tty):
            continue

        pane, _, session, created, started, session_id = parts
        try:
            order = [int(created), int(started), int(session_id.removeprefix("$"))]
        except ValueError:
            continue

        # The recorded order holds tmux's session id, which a rename keeps.
        if (
            metadata.get("tmux_session")
            and not metadata.get("tmux_session_order")
            and metadata["tmux_session"] != session
        ):
            continue

        if metadata.get("tmux_session_order") and metadata["tmux_session_order"] != order:
            continue

        if metadata.get("tmux_pane_identity") and metadata["tmux_pane_identity"] != [
            pane,
            order[1],
        ]:
            continue

        matches.add((session, pane))

    return next(iter(matches)) if len(matches) == 1 else (None, None)


def pane_metadata() -> dict[str, list[dict[str, ty.Any]]]:
    """Live physical panes by TTY; linked aliases use the first sorted location."""
    socket = navigation.current_socket()
    try:
        result = subprocess.run(
            [
                *navigation.server_args(socket),
                "list-panes",
                "-a",
                "-F",
                "#{pane_id}|#{pane_tty}|#{session_name}|#{window_index}|#{session_created}|#{start_time}|#{session_id}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=0.5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise navigation.TmuxUnavailable(str(error)) from error
    locations: dict[str, list[dict[str, ty.Any]]] = {}
    seen: set[tuple[str, int]] = set()
    for line in sorted(result.stdout.splitlines()):
        parts = line.split("|")
        if len(parts) != 7:
            continue
        pane, tty, session, window, created, started, sid = parts
        try:
            order = [int(created), int(started), int(sid.removeprefix("$"))]
        except ValueError:
            continue
        identity = (pane, order[1])
        if identity in seen:
            continue
        seen.add(identity)
        location = {
            "tty": tty,
            "tmux_session": session,
            "tmux_window": window,
            "tmux_pane_identity": [pane, order[1]],
            "tmux_session_order": order,
            **({"tmux_socket": socket} if socket else {}),
        }
        locations.setdefault(tty, []).append(location)
    return locations
