"""Which brief file belongs to which harness session.

A brief is attached to one inbox channel - one Claude session or Codex thread -
so it follows that lemon through compaction and resume, and two lemons sharing
a place each have their own. An attachment can also wait on a tmux window for
the first lemon that starts there after it was requested, which is how a brief
reaches a session that `place open` has only just created.

"Starts after" means a channel that was not live when the brief was
requested: a new one, or one revived from the archive. Timestamps and row ids
can't say it: a notification on an existing channel refreshes that row's
`created_at`, and a revived session keeps its old row.
"""

import dataclasses
import json
import sqlite3
import time
from collections import abc
from pathlib import Path

from ..inbox import db
from . import session


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
    conn.execute("DELETE FROM pending_briefs WHERE path = ?", (str(path),))
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


def live_channels(conn: sqlite3.Connection) -> list[str]:
    """The channels live and placed in tmux now; a lemon on any other channel starts, returns,
    or is first placed after this.

    A lemon already running but not yet placed - a Codex whose row the watcher hasn't
    located - is left out, so it can still claim a brief waiting on its window.
    """
    return [
        row["channel"]
        for row in conn.execute(
            "SELECT DISTINCT channel FROM notifications WHERE status != 'archived' "
            "AND json_extract(metadata, '$.tmux_session') IS NOT NULL ORDER BY channel"
        )
    ]


def attach_pending(
    conn: sqlite3.Connection,
    tmux_session: str,
    tmux_window: str,
    path: Path,
    live_before: abc.Iterable[str],
    tmux_window_id: str = "",
    name: str = "",
) -> None:
    """Attach *path* to the first lemon in this window on a channel not in *live_before*.

    *tmux_window_id* follows the window if tmux renumbers it; without one, the
    window is the index *tmux_window*. A *name* is given to the lemon's session
    when it claims the brief.
    """
    conn.execute(
        """
        INSERT OR REPLACE INTO pending_briefs
            (tmux_session, tmux_window, path, tmux_window_id, live_before, requested_at, name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tmux_session,
            tmux_window,
            str(path),
            tmux_window_id,
            json.dumps(sorted(set(live_before))),
            time.time(),
            name,
        ),
    )
    conn.commit()


def _where_now(row: sqlite3.Row) -> tuple[str, str]:
    """The pending row's window as (session, index), following its ID when tmux knows it."""
    if row["tmux_window_id"]:
        now = session.window_location(row["tmux_window_id"])
        if now[0]:
            return now

    return row["tmux_session"], row["tmux_window"]


def _first_lemon_after(
    conn: sqlite3.Connection, tmux_session: str, tmux_window: str, live_before: list[str]
) -> str:
    row = conn.execute(
        f"""
        SELECT channel FROM notifications
        WHERE json_extract(metadata, '$.tmux_session') = ?
          AND CAST(json_extract(metadata, '$.tmux_window') AS TEXT) = ?
          AND status != 'archived'
          AND channel NOT IN ({",".join("?" * len(live_before))})
          AND channel NOT IN (SELECT channel FROM session_briefs)
        ORDER BY id LIMIT 1
        """,
        (tmux_session, tmux_window, *live_before),
    ).fetchone()
    return row["channel"] if row else ""


def claim_pending(conn: sqlite3.Connection) -> None:
    """Hand each waiting brief to its lemon, if that lemon has started.

    Runs before every lookup rather than from the hooks that record sessions, so
    which lemon gets a brief never depends on when someone happened to look.
    A brief attached by channel since it started waiting stops waiting.
    """
    conn.execute(
        "DELETE FROM pending_briefs WHERE EXISTS (SELECT 1 FROM session_briefs s "
        "WHERE s.path = pending_briefs.path AND s.attached_at > pending_briefs.requested_at)"
    )
    conn.commit()
    for row in conn.execute("SELECT * FROM pending_briefs").fetchall():
        channel = _first_lemon_after(conn, *_where_now(row), json.loads(row["live_before"]))
        if not channel:
            continue

        attach(conn, channel, Path(row["path"]))
        if row["name"] and (newest := db.get_by_channel(conn, channel, unread_only=False)):
            db.update_name(conn, newest.id, row["name"])
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
