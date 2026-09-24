"""An optional emoji per harness session, shown before its name.

It marks the actor - one Claude session or Codex thread, i.e. one inbox channel
- rather than a place or a tmux session, since neither maps one-to-one onto the
lemons working in it. A channel survives compaction and resume, so the emoji
does too; a fresh lemon in the same place starts without one.

Display state only: nothing reads the emoji to decide who wrote what, so it can
change or vanish at any time.
"""

import sqlite3
import time


def _bare(emoji: str) -> str:
    """*emoji* without the variation selector that only picks its presentation."""
    return emoji.replace("\ufe0f", "")


def in_use(conn: sqlite3.Connection) -> list[dict]:
    """Emojis held by live sessions - those whose newest inbox row isn't archived.

    Snoozed sessions are live. An archived session keeps its emoji, so a resume
    shows it again, but doesn't hold it against anyone else meanwhile.
    """
    rows = conn.execute(
        """
        SELECT e.emoji, n.id, n.channel, n.name, json_extract(n.metadata, '$.cwd') AS cwd
        FROM session_emoji e
        JOIN notifications n ON n.id = (
            SELECT MAX(id) FROM notifications WHERE channel = e.channel
        )
        WHERE n.status != 'archived'
        ORDER BY e.set_at
        """
    ).fetchall()
    return [dict(row) for row in rows]


def holder(conn: sqlite3.Connection, emoji: str, excluding: str) -> dict | None:
    """The live session other than *excluding* already showing *emoji*, if any."""
    return next(
        (
            held
            for held in in_use(conn)
            if held["channel"] != excluding and _bare(held["emoji"]) == _bare(emoji)
        ),
        None,
    )


def by_channel(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["channel"]: row["emoji"] for row in conn.execute("SELECT * FROM session_emoji")}


def set_emoji(conn: sqlite3.Connection, channel: str, emoji: str) -> None:
    conn.execute(
        """
        INSERT INTO session_emoji (channel, emoji, set_at) VALUES (?, ?, ?)
        ON CONFLICT(channel) DO UPDATE SET emoji = excluded.emoji, set_at = excluded.set_at
        """,
        (channel, emoji, time.time()),
    )
    conn.commit()


def clear(conn: sqlite3.Connection, channel: str) -> None:
    conn.execute("DELETE FROM session_emoji WHERE channel = ?", (channel,))
    conn.commit()
