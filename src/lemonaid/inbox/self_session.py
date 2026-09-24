"""Which inbox channel is the lemon calling from this tmux pane?

A channel (backend session id) is the identity; a tty is only where the pane
happens to be now, and ttys are reused. So a channel is chosen only when its
newest live row records this pane's tty, tmux session, and window, and exactly
one channel does. Anything else is an error that names `--id` or `--channel`,
never a guess at the likeliest row.
"""

import sqlite3
import subprocess
import typing as ty

from ..log import get_logger
from . import db

_log = get_logger("inbox.self_session")

_GUIDANCE = "Name it with --id or --channel instead (see `lemonaid inbox list --json`)."


class PaneLocation(ty.NamedTuple):
    tty: str
    session: str
    window: str


def pane_location(pane_id: str) -> PaneLocation | None:
    """Where *pane_id* is, or None if tmux can't say."""
    try:
        result = subprocess.run(
            [
                "tmux",
                "display-message",
                "-t",
                pane_id,
                "-p",
                "#{pane_tty}\t#{session_name}\t#{window_index}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("could not locate pane %s: %s", pane_id, e)
        return None

    fields = result.stdout.rstrip("\n").split("\t")
    if len(fields) != 3 or not all(fields):
        return None

    return PaneLocation(*fields)


def _live_newest_rows(conn: sqlite3.Connection) -> list[db.Notification]:
    """Each channel's newest row, for channels whose newest row isn't archived."""
    rows = conn.execute(
        """
        SELECT n.* FROM notifications n
        JOIN (SELECT channel, MAX(id) AS max_id FROM notifications GROUP BY channel) latest
            ON n.id = latest.max_id
        WHERE n.status != 'archived'
        """
    ).fetchall()
    return [db.Notification.from_row(row) for row in rows]


def _recorded_at(n: db.Notification, where: PaneLocation) -> bool:
    return (
        n.metadata.get("tty") == where.tty
        and n.metadata.get("tmux_session") == where.session
        and str(n.metadata.get("tmux_window", "")) == where.window
    )


def resolve(conn: sqlite3.Connection, where: PaneLocation) -> tuple[str, str]:
    """(channel, "") for the one live session recorded at *where*, else ("", why not)."""
    live = _live_newest_rows(conn)
    matches = sorted({n.channel for n in live if _recorded_at(n, where)})
    if len(matches) == 1:
        return matches[0], ""

    at = f"{where.session}:{where.window} ({where.tty})"
    if matches:
        return "", f"{len(matches)} live sessions are recorded at {at}: {', '.join(matches)}. {_GUIDANCE}"

    on_tty = [n for n in live if n.metadata.get("tty") == where.tty]
    detail = (
        f"; {len(on_tty)} on that tty lack a matching tmux session and window"
        if on_tty
        else "; it appears once the lemon has sent a notification"
    )
    return "", f"No live session is recorded at {at}{detail}. {_GUIDANCE}"
