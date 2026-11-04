"""The channel a brief was attached to when it went to the attic.

Archiving detaches a brief, so without this nothing says which session to
attach it to again when its lemon is resumed.
"""

import sqlite3


def remember(conn: sqlite3.Connection, lemon_id: str, path: str) -> None:
    """Record the channel *path* is attached to now, if any. Commits nothing."""
    conn.execute(
        "INSERT OR REPLACE INTO archived_channels (lemon_id, channel)"
        " SELECT ?, channel FROM session_briefs WHERE path = ? ORDER BY attached_at DESC LIMIT 1",
        (lemon_id, path),
    )


def of(conn: sqlite3.Connection, lemon_id: str) -> str:
    """The channel *lemon_id*'s brief was attached to when it was archived, or ""."""
    row = conn.execute(
        "SELECT channel FROM archived_channels WHERE lemon_id = ?", (lemon_id,)
    ).fetchone()
    return row["channel"] if row else ""
