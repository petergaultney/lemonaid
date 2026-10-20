"""Carry a Claude lemon's brief across `/clear`, which starts a new session in the same process.

Claude waits for the `SessionEnd` hooks (reason `clear`) before it starts the new session,
so when the new session's `SessionStart` hook runs, the old row already records the clear.
The process keeps its terminal, so the old row's tty is the new session's tty.
"""

import sqlite3
import time
from pathlib import Path

from ...inbox import db
from .. import attached
from . import state as handoff_state
from . import transfer as handoff_transfer

_RECENT_SECONDS = 60


def cleared(
    conn: sqlite3.Connection, channel: str, tty: str, now: float
) -> tuple[str, Path] | None:
    """The channel that `/clear` last ended on *tty* and its brief, if it has one.

    Only the last clear on the terminal counts, even when its row is archived: an older
    clear ended an earlier session.
    """
    row = conn.execute(
        """SELECT channel, status FROM notifications
           WHERE channel LIKE 'claude:%' AND channel != ?
             AND json_extract(metadata, '$.exit_reason') = 'clear'
             AND json_extract(metadata, '$.tty') = ?
             AND json_extract(metadata, '$.exited_at') > ?
           ORDER BY json_extract(metadata, '$.exited_at') DESC LIMIT 1""",
        (channel, tty, now - _RECENT_SECONDS),
    ).fetchone()
    if row is None or row["status"] == "archived":
        return None

    path = attached.by_channel(conn, [row["channel"]]).get(row["channel"])
    return (row["channel"], path) if path else None


def _other_pane(old: db.Notification, new: db.Notification) -> bool:
    """Whether the rows name different tmux panes: another pane has reused the tty."""
    recorded = old.metadata.get("tmux_pane_identity"), new.metadata.get("tmux_pane_identity")
    return None not in recorded and recorded[0] != recorded[1]


def carry(conn: sqlite3.Connection, source: str, path: Path, target: str) -> bool:
    """Move *path* and the inbox name from *source* to *target*; whether it moved.

    A brief waiting on *target*'s window claims it first. Nothing moves when a handoff
    owns the brief, when *source* no longer holds it, when *target* has a brief or no
    inbox row, or when the two rows name different tmux panes.
    """
    attached.claim_pending(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        holder = conn.execute(
            "SELECT channel FROM session_briefs WHERE path = ?", (str(path),)
        ).fetchone()
        old = db.get_by_channel(conn, source, unread_only=False)
        new = db.get_by_channel(conn, target, unread_only=False)
        if (
            holder is None
            or holder["channel"] != source
            or old is None
            or new is None
            or attached.by_channel(conn, [target])
            or _other_pane(old, new)
            or handoff_state.pending_source(conn, path, source, time.time())
        ):
            conn.rollback()
            return False

        handoff_transfer.move(conn, str(path), source, target, "brief-clear-transfer")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise

    return True
