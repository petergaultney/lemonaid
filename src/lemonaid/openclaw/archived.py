"""A lemon follows its OpenClaw session, as a Claude or Codex lemon follows its harness:
archiving the session archives the lemon; restoring it, by hand or by a new message in its
room, brings the lemon back; and so does a new message in a session whose lemon was archived
in lemonaid, from the grove or the inbox.
"""

import sqlite3
import time
from collections import abc

from ..inbox import db, ended
from . import sessions

BY = "openclaw archive"


def _restore(conn: sqlite3.Connection, channel: str, interacted: float) -> bool:
    """Bring back the channel's newest row, if it is archived and either this archived it or
    its session has had a message since (*interacted*, in seconds)."""
    return bool(
        conn.execute(
            "UPDATE notifications SET status = 'read', read_at = ?,"
            " metadata = json_remove(metadata, '$.ended')"
            " WHERE id = (SELECT MAX(id) FROM notifications WHERE channel = ?)"
            " AND status = 'archived'"
            " AND (json_extract(metadata, '$.ended.by') = ?"
            " OR COALESCE(json_extract(metadata, '$.ended.at'), 0) < ?)",
            (time.time(), channel, BY, interacted),
        ).rowcount
    )


def follow(
    conn: sqlite3.Connection,
    archived: abc.Mapping[str, str],
    found: abc.Mapping[str, sessions.Session],
) -> tuple[list[str], list[str]]:
    """Archive the lemon of each session in *archived* (key to OpenClaw's archive reason), and
    bring back an archived lemon whose session is *found* and not archived, when this archived
    it or the session has had a message since. Returns (archived, restored) channels."""
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
            " AND status = 'archived'",
            (sessions.PREFIX + "%",),
        ).fetchall()
        if (key := sessions.session_key(channel)) in found
        and key not in archived
        and _restore(conn, channel, found[key].interacted_ms / 1000)
    ]
    conn.commit()
    return gone, back
