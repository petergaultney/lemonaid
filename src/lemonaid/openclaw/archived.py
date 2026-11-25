"""A lemon follows its OpenClaw session's archive state, as a Claude or Codex lemon follows
its harness's exit: archiving the session archives the lemon, and restoring it, whether by
hand or by a new message in its room, brings the lemon back.
"""

import sqlite3
import time
from collections import abc

from ..inbox import db, ended
from . import sessions

BY = "openclaw archive"


def _restore(conn: sqlite3.Connection, channel: str) -> bool:
    """Bring back the channel's newest row, if this archived it and nothing has since."""
    return bool(
        conn.execute(
            "UPDATE notifications SET status = 'read', read_at = ?,"
            " metadata = json_remove(metadata, '$.ended')"
            " WHERE id = (SELECT MAX(id) FROM notifications WHERE channel = ?)"
            " AND status = 'archived' AND json_extract(metadata, '$.ended.by') = ?",
            (time.time(), channel, BY),
        ).rowcount
    )


def follow(
    conn: sqlite3.Connection, archived: abc.Mapping[str, str], listed: abc.Set[str]
) -> tuple[list[str], list[str]]:
    """Archive the lemon of each session in *archived* (key to OpenClaw's archive reason),
    and bring back each lemon this archived whose session is *listed* and no longer
    archived. Returns (archived, restored) channels."""
    active = [
        (channel, sessions.session_key(channel))
        for (channel,) in conn.execute(
            "SELECT DISTINCT channel FROM notifications WHERE channel LIKE ?"
            " AND status != 'archived'",
            (sessions.PREFIX + "%",),
        ).fetchall()
    ]
    gone = [
        channel
        for channel, key in active
        if key in archived
        and db.archive_channel(
            conn,
            channel,
            f"archived in OpenClaw ({archived[key] or 'no reason given'})",
            cause=ended.ARCHIVED,
            by=BY,
            commit=False,
        )
    ]
    back = [
        channel
        for (channel,) in conn.execute(
            "SELECT DISTINCT channel FROM notifications WHERE channel LIKE ?"
            " AND status = 'archived' AND json_extract(metadata, '$.ended.by') = ?",
            (sessions.PREFIX + "%", BY),
        ).fetchall()
        if (key := sessions.session_key(channel)) in listed
        and key not in archived
        and _restore(conn, channel)
    ]
    conn.commit()
    return gone, back
