"""Briefs that no live lemon owns: no parent link, or a parent whose session is gone."""

import functools
import sqlite3
import subprocess
from collections import abc

from ..brief import attached, identity, lemon
from ..lineage import links
from ..log import get_logger
from ..tmux import navigation

_log = get_logger("watch.briefs.orphans")

_TIMEOUT_SECONDS = 5


def live_sessions(socket: str) -> frozenset[str] | None:
    """The running sessions on the tmux server at *socket* (this process's own server when
    empty), or None when tmux could not say."""
    try:
        result = subprocess.run(
            [*navigation.server_args(socket), "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        _log.warning("tmux list-sessions failed: %s", error)
        return None

    return frozenset(result.stdout.splitlines())


def find(
    conn: sqlite3.Connection,
    skip: abc.Collection[str],
    live: abc.Callable[[str], abc.Set[str] | None],
) -> list[str]:
    """Lemon-IDs of attached briefs, other than *skip*, that no live lemon owns.

    *live* maps a tmux socket to that server's running sessions, each socket asked once. When
    it returns None (tmux could not say) a parent on that server counts as live, so a tmux
    failure leaves briefs with a parent link quiet.
    """
    sessions = functools.cache(live)
    everything = attached.everything(conn)
    where = {
        entry.path: (
            entry.tmux_session,
            (entry.notification.metadata.get("tmux_socket") or "") if entry.notification else "",
        )
        for entry in everything
    }
    found: list[str] = []
    for entry in everything:
        if not entry.channel:
            continue

        try:
            lemon_id = lemon.current(conn, identity.from_path(entry.path))
        except (OSError, ValueError) as error:
            _log.warning("Skipping brief %s: %s", entry.path, error)
            continue

        if lemon_id in skip:
            continue

        parent = links.parent_of(conn, lemon_id)
        parent_brief = lemon.brief_of(conn, parent) if parent else None
        session, socket = where.get(parent_brief, ("", "")) if parent_brief else ("", "")
        if not parent or ((running := sessions(socket)) is not None and session not in running):
            found.append(lemon_id)

    return found
