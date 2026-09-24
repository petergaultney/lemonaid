"""Which brief file belongs to which harness session.

A brief is attached to one inbox channel - one Claude session or Codex thread -
so it follows that lemon through compaction and resume, and two lemons sharing
a place each have their own. An attachment can also wait on a tmux window for
the first lemon that starts there after it was requested, which is how a brief
reaches a session that `place open` has only just created.

"Starts after" means a channel the inbox had never seen when the brief was
requested. Timestamps can't say it: a notification on an existing channel
refreshes that row's `created_at`.
"""

import dataclasses
import sqlite3
import time
from collections import abc
from pathlib import Path

from ..inbox import db


@dataclasses.dataclass(frozen=True)
class Attachment:
    path: Path
    channel: str  # "" while pending
    tmux_session: str
    tmux_window: str
    notification: db.Notification | None


def attach(conn: sqlite3.Connection, channel: str, path: Path) -> str:
    """Attach *path* to *channel*. Returns the channel it moved from, or ""."""
    previous = conn.execute(
        "SELECT channel FROM session_briefs WHERE path = ? AND channel != ?",
        (str(path), channel),
    ).fetchone()
    conn.execute("DELETE FROM session_briefs WHERE path = ?", (str(path),))
    conn.execute(
        "INSERT OR REPLACE INTO session_briefs (channel, path, attached_at) VALUES (?, ?, ?)",
        (channel, str(path), time.time()),
    )
    conn.commit()
    return previous["channel"] if previous else ""


def detach(conn: sqlite3.Connection, channel: str) -> Path | None:
    """Remove *channel*'s brief, returning the path it had."""
    row = conn.execute("SELECT path FROM session_briefs WHERE channel = ?", (channel,)).fetchone()
    conn.execute("DELETE FROM session_briefs WHERE channel = ?", (channel,))
    conn.commit()
    return Path(row["path"]) if row else None


def newest_id(conn: sqlite3.Connection) -> int:
    """The newest inbox row now; a lemon whose row is newer started after this call."""
    return conn.execute("SELECT COALESCE(MAX(id), 0) FROM notifications").fetchone()[0]


def attach_pending(
    conn: sqlite3.Connection, tmux_session: str, tmux_window: str, path: Path, after_id: int
) -> None:
    """Attach *path* to the first new channel in this window with a row newer than *after_id*."""
    conn.execute(
        """
        INSERT OR REPLACE INTO pending_briefs
            (tmux_session, tmux_window, path, after_id, requested_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (tmux_session, tmux_window, str(path), after_id, time.time()),
    )
    conn.commit()


def _first_lemon_after(
    conn: sqlite3.Connection, tmux_session: str, tmux_window: str, after_id: int
) -> str:
    row = conn.execute(
        """
        SELECT channel FROM notifications
        WHERE json_extract(metadata, '$.tmux_session') = ?
          AND CAST(json_extract(metadata, '$.tmux_window') AS TEXT) = ?
          AND id > ?
          AND channel NOT IN (SELECT channel FROM notifications WHERE id <= ?)
          AND channel NOT IN (SELECT channel FROM session_briefs)
        ORDER BY id LIMIT 1
        """,
        (tmux_session, tmux_window, after_id, after_id),
    ).fetchone()
    return row["channel"] if row else ""


def claim_pending(conn: sqlite3.Connection) -> None:
    """Hand each waiting brief to its lemon, if that lemon has started.

    Runs before every lookup rather than from the hooks that record sessions, so
    which lemon gets a brief never depends on when someone happened to look.
    """
    for row in conn.execute("SELECT * FROM pending_briefs").fetchall():
        channel = _first_lemon_after(conn, row["tmux_session"], row["tmux_window"], row["after_id"])
        if not channel:
            continue

        attach(conn, channel, Path(row["path"]))
        conn.execute(
            "DELETE FROM pending_briefs WHERE tmux_session = ? AND tmux_window = ?",
            (row["tmux_session"], row["tmux_window"]),
        )
        conn.commit()


def by_channel(conn: sqlite3.Connection, channels: abc.Iterable[str]) -> dict[str, Path]:
    """The attached brief of each channel that has one."""
    wanted = list(channels)
    rows = conn.execute(
        f"SELECT channel, path FROM session_briefs WHERE channel IN ({','.join('?' * len(wanted))})",
        wanted,
    ).fetchall()
    return {row["channel"]: Path(row["path"]) for row in rows}


def for_rows(conn: sqlite3.Connection, rows: abc.Iterable[db.Notification]) -> dict[str, Path]:
    """The attached brief of each row's channel, after claiming any now due."""
    claim_pending(conn)
    return by_channel(conn, (row.channel for row in rows))


def everything(conn: sqlite3.Connection) -> list[Attachment]:
    """Every attachment, then every pending one."""
    attached = [
        Attachment(
            Path(row["path"]),
            row["channel"],
            (found.metadata.get("tmux_session") or "") if found else "",
            str(found.metadata.get("tmux_window") or "") if found else "",
            found,
        )
        for row in conn.execute("SELECT * FROM session_briefs ORDER BY attached_at").fetchall()
        for found in [db.get_by_channel(conn, row["channel"], unread_only=False)]
    ]
    pending = [
        Attachment(Path(row["path"]), "", row["tmux_session"], row["tmux_window"], None)
        for row in conn.execute("SELECT * FROM pending_briefs ORDER BY requested_at").fetchall()
    ]
    return [*attached, *pending]
