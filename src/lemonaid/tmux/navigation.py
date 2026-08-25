"""tmux integration for lemonaid."""

import json
import os
import subprocess
from pathlib import Path

from ..log import get_logger

_log = get_logger("tmux.navigation")

# Returned as the session when a cwd matches panes in more than one session.
# Distinct from "no match" because the responses differ: nothing found means the
# session is gone and may be recreated, while several found means one of them is
# the right one and spawning another would add to the confusion.
AMBIGUOUS = "?ambiguous"


def get_state_path() -> Path:
    """Get the path to the lemonaid state directory."""
    state_dir = Path.home() / ".local" / "state" / "lemonaid"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_back_file() -> Path:
    """Get the path to the back state file."""
    return get_state_path() / "tmux-back.json"


def is_inside_tmux() -> bool:
    """Check if we're running inside tmux."""
    return bool(os.environ.get("TMUX"))


def get_current_location() -> tuple[str | None, str | None]:
    """Get the current tmux session and pane target.

    Returns (session_name, pane_id) where pane_id is like '%5'.
    The pane_id uniquely identifies a pane across all sessions.
    """
    if not is_inside_tmux():
        return None, None

    # TMUX_PANE gives us the pane ID directly (e.g., '%5')
    pane_id = os.environ.get("TMUX_PANE")
    if not pane_id:
        return None, None

    # Get the session name for this pane
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-t", pane_id, "-p", "#{session_name}"],
            capture_output=True,
            text=True,
            check=True,
        )
        session_name = result.stdout.strip()
        return session_name, pane_id
    except subprocess.CalledProcessError:
        return None, None


class TmuxUnavailable(Exception):
    """tmux could not answer, which is not the same as answering "no"."""


def server_args(socket: str | None) -> list[str]:
    """`tmux`, aimed at *socket* when there is one.

    A tmux command with no `-S` goes to whichever server the calling process is
    attached to. That is right for anything acting on "here" and wrong for
    anything asking about a session recorded elsewhere, which cannot be seen
    from the wrong server and so reads as gone.
    """
    return ["tmux", "-S", socket] if socket else ["tmux"]


def get_pane_for_tty(tty: str, socket: str | None = None) -> tuple[str | None, str | None]:
    """Find the tmux session and pane for a given TTY.

    Returns (session_name, pane_id), or (None, None) when no pane has that tty.

    Raises TmuxUnavailable if tmux itself failed, so a caller deciding whether a
    session is dead can tell that apart from a pane that is genuinely gone. A
    *socket* naming a server that is gone is exactly that failure, not an
    answer: the session may be dead, but a server that never comes back would
    otherwise archive its rows on the strength of a connection error.
    """
    try:
        # List all panes with their TTY and pane ID
        result = subprocess.run(
            [
                *server_args(socket),
                "list-panes",
                "-a",
                "-F",
                "#{pane_tty}|#{session_name}|#{pane_id}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) == 3:
                pane_tty, session_name, pane_id = parts
                if pane_tty == tty:
                    return session_name, pane_id

    except subprocess.CalledProcessError as e:
        _log.warning("could not list panes to resolve %s: %s", tty, e)
        raise TmuxUnavailable(str(e)) from e

    return None, None


def locations_by_tty(socket: str | None = None) -> dict[str, tuple[str, str]]:
    """Where every pane is sitting, as tty -> (session_name, window_index).

    Distinct from `get_pane_for_tty`, which answers "is it still there" and is
    used for auto-archiving. This answers "where is it", which is what lets a
    session be rebuilt after the tmux server is gone - including for idle
    sessions, which would otherwise never re-record their own location.

    Returned whole rather than looked up per tty: the caller has many sessions
    and runs on a poll, so one listing beats one subprocess each.
    """
    try:
        result = subprocess.run(
            [
                *server_args(socket),
                "list-panes",
                "-a",
                "-F",
                "#{pane_tty}|#{session_name}|#{window_index}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as e:
        _log.warning("could not list panes to locate sessions: %s", e)
        return {}

    return {
        parts[0]: (parts[1], parts[2])
        for line in result.stdout.strip().split("\n")
        if len(parts := line.split("|")) == 3
    }


def get_pane_for_cwd(cwd: str, process_name: str | None = None) -> tuple[str | None, str | None]:
    """Find a tmux pane by its current working directory.

    Optionally filter by a process running in the pane.
    Returns (session_name, pane_id) or (None, None) if not found.

    A directory does not identify a session: two agents started in one worktree
    at different times both match, as do a worktree's own session and any other
    that has a window open there. Rather than take whichever tmux happens to list
    first - which sends you somewhere unrelated and looks like a switching bug -
    that returns `(AMBIGUOUS, None)` and names the candidates in the log.

    *process_name* is matched against `pane_current_command`, which is the process
    title and not necessarily the command you launched: Claude sets its title to
    its version (`2.1.220`), so passing "claude" matches nothing and every
    candidate is discarded. Callers relying on this filter to find an agent pane
    should expect it to find none.
    """
    try:
        # List all panes with their cwd, current command, session, and pane ID
        result = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{pane_current_path}|#{pane_current_command}|#{session_name}|#{pane_id}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        _log.warning("could not list panes to resolve %s: %s", cwd, e)
        return None, None

    matches: list[tuple[str, str]] = []
    for line in result.stdout.strip().split("\n"):
        parts = line.split("|")
        if len(parts) != 4:
            continue

        pane_cwd, pane_cmd, session_name, pane_id = parts
        if pane_cwd == cwd and (not process_name or process_name in pane_cmd):
            matches.append((session_name, pane_id))

    if not matches:
        return None, None

    sessions = {session for session, _ in matches}
    if len(sessions) > 1:
        _log.warning(
            "%s is the cwd of panes in %d sessions (%s); not guessing which one was meant",
            cwd,
            len(sessions),
            ", ".join(sorted(sessions)),
        )
        return AMBIGUOUS, None

    return matches[0]


def get_pane_for_session(session: str) -> tuple[str | None, str | None]:
    """Find the active pane of a session by name.

    Returns (session_name, pane_id) or (None, None) if no such session.
    """
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-t", session, "-F", "#{session_name}|#{pane_id}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None, None  # tmux errors rather than returning empty for an unknown target

    for line in result.stdout.strip().split("\n"):
        parts = line.split("|")
        # An exact match only: `-t` accepts prefixes, so asking for 'notes' would
        # otherwise resolve to a session called 'notes-old'.
        if len(parts) == 2 and parts[0] == session:
            return parts[0], parts[1]

    return None, None


def save_back_location(session: str, pane_id: str) -> None:
    """Save a location for the 'back' command."""
    back_file = get_back_file()
    data = {"session": session, "pane_id": pane_id}
    back_file.write_text(json.dumps(data))


def load_back_location() -> tuple[str | None, str | None]:
    """Load the saved 'back' location."""
    back_file = get_back_file()
    if not back_file.exists():
        return None, None

    try:
        data = json.loads(back_file.read_text())
        return data.get("session"), data.get("pane_id")
    except (json.JSONDecodeError, KeyError):
        return None, None


def switch_to_pane(session: str, pane_id: str, save_current: bool = True) -> bool:
    """
    Switch to a tmux session and pane.

    If save_current=True, saves the current location for 'back' command.

    Args:
        session: The session name (for context, though pane_id is globally unique)
        pane_id: The pane ID (e.g., '%5') - globally unique in tmux
        save_current: Whether to save current location before switching
    """
    # Save current location before switching
    if save_current:
        current_session, current_pane = get_current_location()
        if current_session and current_pane:
            save_back_location(current_session, current_pane)

    try:
        # Switch client to the target pane
        # tmux will automatically switch to the right session/window
        subprocess.run(
            ["tmux", "switch-client", "-t", pane_id],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def go_back() -> bool:
    """Switch back to the previously saved location."""
    session, pane_id = load_back_location()
    if session is None or pane_id is None:
        return False

    # Don't save current as new back location (would cause ping-pong)
    return switch_to_pane(session, pane_id, save_current=False)


def swap_back_location(current_session: str, current_pane_id: str) -> tuple[str | None, str | None]:
    """Atomically swap: save current location, return previous target.

    Returns (session, pane_id) of the target to switch to, or (None, None).
    """
    # Load target before overwriting
    target_session, target_pane_id = load_back_location()

    # Save current as new back location (enables ping-pong)
    save_back_location(current_session, current_pane_id)

    return target_session, target_pane_id
