"""tmux integration for lemonaid."""

import json
import os
import subprocess
import typing as ty
from collections import abc
from pathlib import Path

from ..log import get_logger

_log = get_logger("tmux.navigation")

# Returned as the session when a cwd matches panes in more than one session.
# Distinct from "no match" because the responses differ: nothing found means the
# session is gone and may be recreated, while several found means one of them is
# the right one and spawning another would add to the confusion.
AMBIGUOUS = "?ambiguous"
_QUERY_TIMEOUT_SECONDS = 0.5


def get_state_path() -> Path:
    """The lemonaid state directory, `LEMONAID_STATE_DIR` overriding the default."""
    override = os.environ.get("LEMONAID_STATE_DIR")
    state_dir = (
        Path(override).expanduser() if override else Path.home() / ".local" / "state" / "lemonaid"
    )
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


def get_pane_for_tty(
    tty: str, socket: str | None = None, not_after: float | None = None
) -> tuple[str | None, str | None]:
    """Find the tmux session and pane for a given TTY.

    Returns (session_name, pane_id), or (None, None) when no pane has that tty.

    Raises TmuxUnavailable if tmux itself failed, so a caller deciding whether a
    session is dead can tell that apart from a pane that is genuinely gone. A
    *socket* naming a server that is gone is exactly that failure, not an
    answer: the session may be dead, but a server that never comes back would
    otherwise archive its rows on the strength of a connection error.

    *not_after* is when the thing being looked for was last known to exist. The
    OS reuses tty device names, so after a reboot every recorded tty is likely
    to name some unrelated pane; a tmux session created later than the record
    cannot be the one it refers to. Without it a stale row matches whatever
    inherited its tty, which reads as "still running" for a session that is not.

    This narrows the lie without ending it - two records can still point at one
    reused tty inside a long-lived tmux session. A tty is where a session was,
    not which session it is. The SessionStart hook is what makes the location a
    reported fact rather than one inferred from a device name.
    """
    try:
        # List all panes with their TTY and pane ID
        result = subprocess.run(
            [
                *server_args(socket),
                "list-panes",
                "-a",
                "-F",
                "#{pane_tty}|#{session_name}|#{pane_id}|#{session_created}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) == 4:
                pane_tty, session_name, pane_id, created = parts
                if pane_tty != tty:
                    continue

                if not_after is not None and created.isdigit() and int(created) > not_after:
                    continue

                return session_name, pane_id

    except subprocess.CalledProcessError as e:
        _log.warning("could not list panes to resolve %s: %s", tty, e)
        raise TmuxUnavailable(str(e)) from e

    return None, None


# (session creation time, server start time, session id number): the order tmux
# made a session in. The time is in whole seconds and a restore makes many
# sessions in one, so the id breaks ties - but ids start again at $0 in each
# server, so the server's start time comes first. Two servers that both start
# within one second can still tie; the earlier one then lived under a second,
# and no layout worth restoring comes from a server like that.
SessionOrder = tuple[int, int, int]


class PaneLocation(ty.NamedTuple):
    session: str
    window: str
    session_order: SessionOrder | None = None


def _session_order(created: str, server_started: str, session_id: str) -> SessionOrder | None:
    try:
        return int(created), int(server_started), int(session_id.lstrip("$"))
    except ValueError:
        return None


def locations_by_tty(socket: str | None = None) -> dict[str, PaneLocation] | None:
    """Where every pane is sitting, by tty.

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
                "#{pane_tty}|#{session_name}|#{window_index}"
                "|#{session_created}|#{start_time}|#{session_id}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        _log.warning("could not list panes to locate sessions: %s", e)
        return None

    return {
        parts[0]: PaneLocation(parts[1], parts[2], _session_order(*parts[3:]))
        for line in result.stdout.strip().split("\n")
        if len(parts := line.split("|")) == 6
    }


def session_ttys(session: str) -> set[str]:
    """The ttys of every pane in *session*, empty if it is gone or tmux did not answer."""
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-s", "-t", f"={session}", "-F", "#{pane_tty}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        _log.warning("could not list the panes of %s: %s", session, e)
        return set()

    return {line for line in result.stdout.splitlines() if line}


def focused_ttys(socket: str | None = None) -> set[str]:
    """The pane each client is viewing, including the pane behind a focused scratch inbox.

    The scratch pane shares a window with the lemon the user was reading. When
    the user moves into the inbox, tmux selects scratch and marks that lemon as
    the window's last pane. Keep it in view until the client changes windows.
    """
    try:
        result = subprocess.run(
            [
                *server_args(socket),
                "list-clients",
                "-F",
                "#{pane_tty}|#{window_id}|#{@lemonaid_scratch}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        _log.warning("could not list panes to find the focused one: %s", e)
        return set()

    focused: set[str] = set()
    scratch_windows: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        tty, window, scratch = parts
        if tty:
            focused.add(tty)
        if scratch == "1":
            scratch_windows.add(window)

    if not scratch_windows:
        return focused

    try:
        panes = subprocess.run(
            [
                *server_args(socket),
                "list-panes",
                "-a",
                "-F",
                "#{window_id}|#{pane_tty}|#{pane_last}|#{@lemonaid_scratch}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        _log.warning("could not find the pane behind the scratch inbox: %s", e)
        return focused

    for line in panes.stdout.splitlines():
        parts = line.split("|", 3)
        if len(parts) != 4:
            continue
        window, tty, last, scratch = parts
        if window in scratch_windows and last == "1" and scratch != "1" and tty:
            focused.add(tty)

    return focused


def get_pane_for_cwd(
    cwd: str, runs_harness: abc.Callable[[str], bool] | None = None
) -> tuple[str | None, str | None]:
    """Find a tmux pane by its current working directory.

    Returns (session_name, pane_id) or (None, None) if not found.

    A directory does not identify a session: two agents started in one worktree
    at different times both match, as do a worktree's own session and any other
    that has a window open there. Rather than take whichever tmux happens to list
    first - which sends you somewhere unrelated and looks like a switching bug -
    that returns `(AMBIGUOUS, None)` and names the candidates in the log.

    *runs_harness* is asked about each candidate's tty and keeps only the panes
    where it says the agent is running. Two such panes are ambiguous even in one
    session, since each is a different agent. It is given the tty rather than the
    pane's `pane_current_command`, which is a process title and names neither
    agent: Claude sets its title to its version (`2.1.220`), and a Codex started
    through a shell (`tmux new-window ... codex`) reports the shell.
    """
    try:
        result = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{pane_current_path}|#{pane_tty}|#{session_name}|#{pane_id}",
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

        pane_cwd, pane_tty, session_name, pane_id = parts
        if pane_cwd == cwd and (runs_harness is None or runs_harness(pane_tty)):
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

    if runs_harness is not None and len(matches) > 1:
        _log.warning(
            "%s has the agent running in %d panes (%s); not guessing which one was meant",
            cwd,
            len(matches),
            ", ".join(pane for _, pane in matches),
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
