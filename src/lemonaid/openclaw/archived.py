"""A lemon follows its OpenClaw session, as a Claude or Codex lemon follows its harness:
archiving the session archives the lemon; restoring it, by hand or by a new message in its
room, brings the lemon back; and so does a new message in a session whose lemon was archived
in lemonaid, from the grove or the inbox. Its time is its conversation's last message, either
way, as a Claude lemon's is the end of its last turn.
"""

import sqlite3
import time
from collections import abc

from ..inbox import db, ended
from . import sessions

BY = "openclaw archive"


def _restore(conn: sqlite3.Connection, channel: str, interacted: float) -> bool:
    """Bring back the channel's newest row, if it is archived and either this archived it or
    its session has had a message since (*interacted*, in seconds). A lemon a handoff replaced
    stays archived: its brief went to another session, and its old one still answers."""
    return bool(
        conn.execute(
            "UPDATE notifications SET status = 'read', read_at = ?,"
            " metadata = json_remove(metadata, '$.ended')"
            " WHERE id = (SELECT MAX(id) FROM notifications WHERE channel = ?)"
            " AND status = 'archived'"
            " AND (json_extract(metadata, '$.ended.by') = ?"
            " OR (COALESCE(json_extract(metadata, '$.ended.at'), 0) < ?"
            " AND COALESCE(json_extract(metadata, '$.ended.cause'), '') != ?))",
            (time.time(), channel, BY, interacted, ended.REPLACED),
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


def reported(
    conn: sqlite3.Connection, found: abc.Iterable[sessions.Session], added: abc.Set[str]
) -> list[str]:
    """Move each lemon's time (`created_at`) up to its session's last message, or set it there for
    the *added* channels, whose time is when they were added; leaving status alone. Returns the
    channels changed."""
    moved = [
        sessions.channel(each.key)
        for each in found
        if each.interacted_ms
        and conn.execute(
            "UPDATE notifications SET created_at = ?"
            " WHERE id = (SELECT MAX(id) FROM notifications WHERE channel = ?)"
            " AND (created_at < ? OR ?)",
            (
                each.interacted_ms / 1000,
                sessions.channel(each.key),
                each.interacted_ms / 1000,
                sessions.channel(each.key) in added,
            ),
        ).rowcount
    ]
    conn.commit()
    return moved
