"""Moving every client out of a session before it is killed.

Killing a session detaches whoever is looking at it, and that is rarely the
caller: an agent tossing a finished place by key runs in some other session while
you watch the one going away. So each client attached to the doomed session
is switched by name, and teardown is refused if any of them has nowhere to go.
"""

import sqlite3
import subprocess
from collections import abc

from .. import tmux
from ..inbox import db
from ..log import get_logger

_log = get_logger("places.escape")

_QUERY_TIMEOUT_SECONDS = 2


def _live_sessions_by_recency(doomed_session: str) -> list[str]:
    """Other sessions, most recently active first, excluding lemonaid's own."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_activity} #{session_name}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as e:
        _log.warning("could not list sessions to find an escape target: %s", e)
        return []

    return [
        name
        for _, name in sorted(
            (
                (int(activity), name)
                for activity, _, name in (
                    line.partition(" ") for line in result.stdout.splitlines()
                )
                if activity.isdigit() and name != doomed_session and not name.startswith("_lma")
            ),
            reverse=True,
        )
    ]


def _wants_attention(available: abc.Container[str]) -> str:
    """The live session with something unread in the inbox, if any.

    Preferred over bare recency: the most recently *active* session is often the
    one you just left, while the inbox knows which one is actually waiting on you.
    """
    try:
        with db.connect() as conn:
            unread = db.get_unread(conn)
    except sqlite3.Error as e:
        _log.warning("could not read the inbox for an escape target: %s", e)
        return ""

    return next((n.name for n in unread if n.name and n.name in available), "")


def _escape_target(doomed_session: str) -> str:
    """Where to send a client that has no last session of its own to go back to.

    Wherever you came from first - finishing a piece of work usually means going
    back to what you left. Otherwise a session that wants attention, and failing
    that the most recently active one.
    """
    back_session, _ = tmux.navigation.load_back_location()
    if back_session and back_session != doomed_session:
        return back_session

    by_recency = _live_sessions_by_recency(doomed_session)

    return _wants_attention(set(by_recency)) or next(iter(by_recency), "")


class ClientsUnknown(Exception):
    """tmux could not say who is attached, which is not the same as "nobody"."""


def _attached_clients(session: str) -> list[tuple[str, str]]:
    """(client name, the client's last session) for each client attached to *session*."""
    try:
        result = subprocess.run(
            [
                "tmux",
                "list-clients",
                "-t",
                f"={session}",
                "-F",
                "#{client_name}\t#{client_last_session}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise ClientsUnknown(str(e)) from e

    return [
        (name, last)
        for name, _, last in (line.partition("\t") for line in result.stdout.splitlines())
        if name
    ]


def _switch_client(client: str, session: str) -> bool:
    """Move *client* to *session*; tmux picks the session's active pane."""
    try:
        subprocess.run(
            ["tmux", "switch-client", "-c", client, "-t", f"={session}"],
            check=True,
            capture_output=True,
        )
        return True
    except (OSError, subprocess.CalledProcessError) as e:
        _log.warning("could not switch %s to %s: %s", client, session, e)
        return False


def _switch_all(moves: abc.Sequence[tuple[str, str]], session: str) -> str:
    """Switch each client in turn; on the first failure, put back the ones already moved."""
    for i, (client, target) in enumerate(moves):
        if _switch_client(client, target):
            continue

        unrestored = [c for c, _ in moves[:i] if not _switch_client(c, session)]
        return f"Could not switch {client} to '{target}'; nothing was torn down" + (
            f", and {', '.join(unrestored)} could not be moved back to '{session}'"
            if unrestored
            else ""
        )

    return ""


def evacuate(session: str) -> str:
    """Switch every client attached to *session* elsewhere, or say why not.

    Each client goes back to its own last session when that is still alive,
    and otherwise to the shared `_escape_target`. Either every client is moved
    or none is. Returns an error message, or "".
    """
    try:
        clients = _attached_clients(session)
    except ClientsUnknown as e:
        return f"Could not tell who is attached to '{session}' ({e}); nothing was torn down"

    if not clients:
        return ""

    live = _live_sessions_by_recency(session)
    fallback = _escape_target(session)
    moves = [(client, last if last in live else fallback) for client, last in clients]
    stranded = [client for client, target in moves if not target]
    if stranded:
        return (
            f"Nowhere to switch {', '.join(stranded)} to - refusing to kill '{session}' "
            "and detach it"
        )

    return _switch_all(moves, session)
