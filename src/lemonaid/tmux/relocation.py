"""The tmux side of moving a lemon: the session it joins, and the pane it leaves."""

from collections import abc
from pathlib import Path

from . import command, session


def run(socket: str, *args: str) -> str:
    result = command.run(args, socket or None)
    if result.returncode:
        raise ValueError(f"tmux: {(result.stderr or result.stdout).strip()}")

    return result.stdout


def _has_session(socket: str, name: str) -> bool:
    return command.run(["has-session", "-t", f"={name}"], socket or None).returncode == 0


def destination_session(
    socket: str, directory: Path, key: str, protected: abc.Collection[str]
) -> str:
    """The unprotected session already working in *directory*, else a free name for a new one."""
    sessions = {
        name
        for line in run(
            socket, "list-panes", "-a", "-F", "#{session_name}\t#{pane_current_path}"
        ).splitlines()
        for name, _, path in [line.partition("\t")]
        if (path == str(directory) or Path(path).is_relative_to(directory))
        and name not in protected
    }
    if len(sessions) > 1:
        raise ValueError(
            f"Several tmux sessions work in {directory} ({', '.join(sorted(sessions))}); "
            "not guessing which one the lemon joins"
        )

    if sessions:
        return sessions.pop()

    name = session.spawned_name(key, str(directory))
    if _has_session(socket, name):
        raise ValueError(f"A tmux session named {name!r} exists but has no pane in {directory}")

    return name


def ensure_session(socket: str, name: str, directory: str) -> None:
    """Create session *name* in *directory* unless it exists."""
    if not _has_session(socket, name):
        run(socket, "new-session", "-d", "-s", name, "-c", directory)


def pane_location(socket: str, tty: str) -> dict:
    """The pane on *tty* as a hook records it, or only the tty when it can't be told apart."""
    listed = command.run(
        [
            "list-panes",
            "-a",
            "-F",
            "#{pane_tty}|#{pane_id}|#{session_name}|#{window_index}|"
            "#{session_created}|#{start_time}|#{session_id}",
        ],
        socket or None,
    )
    found = [
        parts
        for line in listed.stdout.splitlines()
        if (parts := line.split("|"))[0] == tty and len(parts) == 7
    ]
    if listed.returncode or len(found) != 1:
        return {"tty": tty}

    _, pane, name, window, created, started, session_id = found[0]
    order = [int(created), int(started), int(session_id.removeprefix("$"))]
    return {
        "tty": tty,
        "tmux_session": name,
        "tmux_window": window,
        "tmux_pane_identity": [pane, order[1]],
        "tmux_session_order": order,
    }


def session_of(socket: str, pane: str) -> str:
    return run(socket, "display-message", "-p", "-t", pane, "#{session_name}").strip()


def keep_on_exit(socket: str, pane: str) -> None:
    run(socket, "set-option", "-p", "-t", pane, "remain-on-exit", "on")


def close_pane(socket: str, pane: str, destination: str) -> None:
    """Kill *pane*, first switching clients to *destination* if that closes their session."""
    name = session_of(socket, pane)
    if run(socket, "list-panes", "-s", "-t", f"={name}", "-F", "#{pane_id}").split() == [pane]:
        for client in run(socket, "list-clients", "-t", f"={name}", "-F", "#{client_name}").split():
            run(socket, "switch-client", "-c", client, "-t", f"={destination}")
    run(socket, "kill-pane", "-t", pane)
