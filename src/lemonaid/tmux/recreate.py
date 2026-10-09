"""Resume a detached notification in a uniquely identified tmux session."""

import os
import shlex
import subprocess
from typing import Any

from ..config import Config
from ..log import get_logger
from ..resume import build_resume_command
from . import navigation

_log = get_logger("tmux.recreate")


def _current_socket() -> str | None:
    return navigation.current_socket()


def _stored_order(metadata: dict[str, Any]) -> tuple[int, int, int] | None:
    value = metadata.get("tmux_session_order")
    if not isinstance(value, list) or len(value) != 3:
        return None

    try:
        created, server_started, session_id = (int(part) for part in value)
        return created, server_started, session_id
    except (TypeError, ValueError):
        return None


def _order(created: str, server_started: str, session_id: str) -> tuple[int, int, int] | None:
    try:
        return int(created), int(server_started), int(session_id.lstrip("$"))
    except ValueError:
        return None


def _sessions(socket: str | None) -> dict[str, tuple[tuple[int, int, int] | None, str]] | None:
    try:
        result = subprocess.run(
            [
                *navigation.server_args(socket),
                "list-sessions",
                "-F",
                "#{session_name}|#{session_created}|#{start_time}|#{session_id}|#{session_path}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        _log.warning("could not list tmux sessions for resume: %s", e)
        return None

    sessions = {}
    for line in result.stdout.splitlines():
        parts = line.split("|", 4)
        if len(parts) == 5:
            sessions[parts[0]] = (_order(parts[1], parts[2], parts[3]), parts[4])

    return sessions


def _cwd_sessions(cwd: str, socket: str | None) -> set[str] | None:
    try:
        result = subprocess.run(
            [
                *navigation.server_args(socket),
                "list-panes",
                "-a",
                "-F",
                "#{pane_current_path}|#{session_name}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        _log.warning("could not find tmux sessions at %s: %s", cwd, e)
        return None

    return {
        session
        for line in result.stdout.splitlines()
        if len(parts := line.split("|", 1)) == 2 and parts[0] == cwd and (session := parts[1])
    }


def _destination(metadata: dict[str, Any]) -> tuple[str, str | None] | None:
    current_socket = _current_socket()
    recorded_socket = metadata.get("tmux_socket")
    if recorded_socket and recorded_socket != current_socket:
        _log.info(
            "not resuming %s: recorded tmux server is not the current server",
            metadata.get("channel"),
        )
        return None

    sessions = _sessions(current_socket)
    if sessions is None:
        return None

    recorded = metadata.get("tmux_session")
    stored_order = _stored_order(metadata)
    if isinstance(recorded, str) and recorded in sessions and stored_order is not None:
        current_order = sessions[recorded][0]
        if current_order == stored_order:
            return recorded, current_socket

    cwd = metadata.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None

    candidates = _cwd_sessions(cwd, current_socket)
    if candidates is None:
        return None

    candidates.update(name for name, (_order, path) in sessions.items() if path == cwd)
    if len(candidates) != 1:
        _log.info(
            "not resuming %s: cwd %s identifies %d tmux sessions",
            metadata.get("channel"),
            cwd,
            len(candidates),
        )
        return None

    return next(iter(candidates)), current_socket


def _resume_in_session(
    destination: str, socket: str | None, cwd: str, argv: list[str]
) -> str | None:
    """The tty of the window the session was resumed in, None if it could not be."""
    try:
        result = subprocess.run(
            [
                *navigation.server_args(socket),
                "new-window",
                "-d",
                "-P",
                "-F",
                "#{pane_id}|#{window_id}|#{pane_tty}",
                "-t",
                f"={destination}",
                "-c",
                cwd,
                shlex.join(argv),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        _log.warning("could not resume in tmux session %s: %s", destination, e)
        return None

    pane_id, window_id, tty = [*result.stdout.strip().split("|", 2), "", ""][:3]
    if pane_id and window_id:
        if os.environ.get("TMUX"):
            if navigation.switch_to_pane(destination, pane_id):
                return tty
        else:
            try:
                subprocess.run(
                    [*navigation.server_args(socket), "select-window", "-t", window_id],
                    capture_output=True,
                    check=True,
                    timeout=2,
                )
                subprocess.run(
                    [*navigation.server_args(socket), "attach-session", "-t", f"={destination}"],
                    check=True,
                    timeout=5,
                )
                return tty
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                _log.warning("could not attach to tmux session %s: %s", destination, e)

    if pane_id:
        try:
            subprocess.run(
                [*navigation.server_args(socket), "kill-window", "-t", pane_id],
                capture_output=True,
                check=True,
                timeout=2,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            _log.warning("could not remove failed resume window %s: %s", pane_id, e)

    return None


def resume(metadata: dict[str, Any], config: Config) -> str | None:
    """Resume in a recorded or uniquely cwd-matched session, never a new session.

    Returns the tty the session now runs on, which the inbox row has to be told:
    a Codex session reports its tty only when a turn ends.
    """
    channel = metadata.get("channel", "")
    resumable = build_resume_command(config, channel, metadata)
    destination = _destination(metadata)
    if resumable is None or destination is None:
        return None

    destination_name, socket = destination
    cwd, argv = resumable
    tty = _resume_in_session(destination_name, socket, cwd, argv)
    if tty is None:
        return None

    _log.info("resumed %s in tmux session %s on %s", channel, destination_name, tty)
    return tty


def recreate(metadata: dict[str, Any], config: Config) -> bool:
    return resume(metadata, config) is not None
