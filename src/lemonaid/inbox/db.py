"""SQLite database for lemonaid notifications."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Notification:
    """A notification in the lemonaid inbox."""

    id: int
    channel: str
    message: str
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "unread"
    created_at: float = field(default_factory=time.time)
    read_at: float | None = None
    switch_source: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Notification:
        """Create a Notification from a database row."""
        # Handle columns which may not exist in older DBs
        switch_source = None
        name = None
        with suppress(IndexError, KeyError):
            switch_source = row["switch_source"]
        with suppress(IndexError, KeyError):
            name = row["name"]

        return cls(
            id=row["id"],
            channel=row["channel"],
            message=row["message"],
            name=name,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            status=row["status"],
            created_at=row["created_at"],
            read_at=row["read_at"],
            switch_source=switch_source,
        )

    @property
    def is_read(self) -> bool:
        return self.status == "read"

    @property
    def is_unread(self) -> bool:
        return self.status == "unread"

    @property
    def is_archived(self) -> bool:
        return self.status == "archived"


def get_db_path() -> Path:
    """Get the path to the lemonaid database, following XDG conventions."""
    xdg_data = Path.home() / ".local" / "share"
    lemonaid_dir = xdg_data / "lemonaid"
    lemonaid_dir.mkdir(parents=True, exist_ok=True)
    return lemonaid_dir / "lemonaid.db"


def _init_schema(conn: sqlite3.Connection) -> None:
    """Initialize the database schema.

    This creates the baseline schema (version 0). Migrations bring it up to date.
    Keep this as the original schema to ensure migrations work on fresh databases.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            metadata TEXT,
            status TEXT DEFAULT 'unread',
            created_at REAL NOT NULL,
            read_at REAL
        );

        CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
        CREATE INDEX IF NOT EXISTS idx_notifications_channel ON notifications(channel);
        CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);
    """)
    conn.commit()


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Context manager for database connections."""
    from . import migrations

    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    migrations.run_migrations(conn)

    try:
        yield conn
    finally:
        conn.close()


# --- Queries ---


def get(conn: sqlite3.Connection, notification_id: int) -> Notification | None:
    """Get a notification by ID."""
    row = conn.execute(
        "SELECT * FROM notifications WHERE id = ?",
        (notification_id,),
    ).fetchone()
    return Notification.from_row(row) if row else None


def get_unread(conn: sqlite3.Connection) -> list[Notification]:
    """Get all unread notifications, newest first."""
    rows = conn.execute(
        """
        SELECT * FROM notifications
        WHERE status = 'unread'
        ORDER BY created_at DESC
        """
    ).fetchall()
    return [Notification.from_row(row) for row in rows]


def get_active(conn: sqlite3.Connection, switch_source: str | None = None) -> list[Notification]:
    """Get active sessions (one per channel), unread first then by recency.

    Returns only the most recent notification per channel, excluding archived.
    If switch_source is provided, filters to only notifications from that source
    (or with NULL switch_source for backwards compatibility).
    """
    if switch_source:
        rows = conn.execute(
            """
            SELECT n.* FROM notifications n
            INNER JOIN (
                SELECT channel, MAX(id) as max_id
                FROM notifications
                GROUP BY channel
            ) latest ON n.id = latest.max_id
            WHERE n.status != 'archived'
            AND (n.switch_source = ? OR n.switch_source IS NULL)
            ORDER BY
                CASE n.status WHEN 'unread' THEN 0 ELSE 1 END,
                n.created_at DESC
            """,
            (switch_source,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT n.* FROM notifications n
            INNER JOIN (
                SELECT channel, MAX(id) as max_id
                FROM notifications
                GROUP BY channel
            ) latest ON n.id = latest.max_id
            WHERE n.status != 'archived'
            ORDER BY
                CASE n.status WHEN 'unread' THEN 0 ELSE 1 END,
                n.created_at DESC
            """
        ).fetchall()
    return [Notification.from_row(row) for row in rows]


def get_by_channel(
    conn: sqlite3.Connection,
    channel: str,
    unread_only: bool = True,
) -> Notification | None:
    """Get the most recent notification for a channel."""
    query = "SELECT * FROM notifications WHERE channel = ?"
    if unread_only:
        query += " AND status = 'unread'"
    query += " ORDER BY created_at DESC LIMIT 1"

    row = conn.execute(query, (channel,)).fetchone()
    return Notification.from_row(row) if row else None


# --- Mutations ---


def add(
    conn: sqlite3.Connection,
    channel: str,
    message: str,
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
    upsert: bool = True,
    switch_source: str | None = None,
) -> Notification:
    """Add a notification or update existing one if upsert=True.

    If upsert=True and a notification exists for the channel (even if read or archived),
    it will be updated and set back to unread status.
    """
    now = time.time()
    metadata = metadata or {}

    if upsert:
        # Look for any existing notification for this channel (including read/archived)
        existing = get_by_channel(conn, channel, unread_only=False)
        if existing:
            conn.execute(
                """
                UPDATE notifications
                SET message = ?, name = ?, metadata = ?, created_at = ?, status = 'unread', read_at = NULL, switch_source = ?
                WHERE id = ?
                """,
                (message, name, json.dumps(metadata), now, switch_source, existing.id),
            )
            conn.commit()
            return Notification(
                id=existing.id,
                channel=channel,
                message=message,
                name=name,
                metadata=metadata,
                status="unread",
                created_at=now,
                switch_source=switch_source,
            )

    cursor = conn.execute(
        """
        INSERT INTO notifications (channel, message, name, metadata, created_at, switch_source)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (channel, message, name, json.dumps(metadata), now, switch_source),
    )
    conn.commit()

    return Notification(
        id=cursor.lastrowid or 0,
        channel=channel,
        message=message,
        name=name,
        metadata=metadata,
        created_at=now,
        switch_source=switch_source,
    )


def mark_read(conn: sqlite3.Connection, notification_id: int) -> None:
    """Mark a notification as read."""
    conn.execute(
        "UPDATE notifications SET status = 'read', read_at = ? WHERE id = ?",
        (time.time(), notification_id),
    )
    conn.commit()


def mark_all_read_for_channel(
    conn: sqlite3.Connection,
    channel: str,
    message: str | None = None,
) -> int:
    """Mark all notifications for a channel as read, optionally updating message.

    Args:
        conn: Database connection
        channel: Channel to mark as read
        message: Optional new message (e.g., what Claude is now doing)

    Returns:
        Count of notifications marked as read
    """
    now = time.time()
    if message:
        cursor = conn.execute(
            """
            UPDATE notifications
            SET status = 'read', read_at = ?, message = ?
            WHERE channel = ? AND status = 'unread'
            """,
            (now, message, channel),
        )
    else:
        cursor = conn.execute(
            """
            UPDATE notifications
            SET status = 'read', read_at = ?
            WHERE channel = ? AND status = 'unread'
            """,
            (now, channel),
        )
    conn.commit()
    return cursor.rowcount


def update_message(conn: sqlite3.Connection, channel: str, message: str) -> int:
    """Update the message for a channel without changing read/unread status.

    Used for real-time activity updates while Claude is working.
    Returns count of notifications updated.
    """
    cursor = conn.execute(
        """
        UPDATE notifications
        SET message = ?
        WHERE channel = ?
        """,
        (message, channel),
    )
    conn.commit()
    return cursor.rowcount


def update_name(
    conn: sqlite3.Connection,
    notification_id: int,
    name: str | None,
) -> bool:
    """Update (or clear) the user-override name for a notification.

    When setting a name, preserves the current auto-detected name in metadata.
    When clearing (name=None), restores the auto-detected name if available.

    Returns True if a row was updated.
    """
    notification = get(conn, notification_id)
    if not notification:
        return False

    metadata = dict(notification.metadata)

    if name:
        # Setting a custom name - preserve current name as auto_name (if not already overridden)
        if "auto_name" not in metadata and notification.name:
            metadata["auto_name"] = notification.name
        final_name = name
    else:
        # Clearing - restore auto_name if we have one
        final_name = metadata.pop("auto_name", None)

    cursor = conn.execute(
        """
        UPDATE notifications
        SET name = ?, metadata = ?
        WHERE id = ?
        """,
        (final_name, json.dumps(metadata), notification_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def mark_read_by_tty(conn: sqlite3.Connection, tty: str) -> int:
    """Mark all unread notifications from a TTY as read."""
    cursor = conn.execute(
        """
        UPDATE notifications
        SET status = 'read', read_at = ?
        WHERE json_extract(metadata, '$.tty') = ?
          AND status = 'unread'
        """,
        (time.time(), tty),
    )
    conn.commit()
    return cursor.rowcount


def archive(conn: sqlite3.Connection, notification_id: int) -> None:
    """Archive a notification (session ended or no longer relevant)."""
    conn.execute(
        "UPDATE notifications SET status = 'archived' WHERE id = ?",
        (notification_id,),
    )
    conn.commit()


def clear_old(conn: sqlite3.Connection, days: int = 7) -> int:
    """Delete read/archived notifications older than N days. Returns count."""
    cutoff = time.time() - (days * 24 * 60 * 60)
    cursor = conn.execute(
        """
        DELETE FROM notifications
        WHERE status IN ('read', 'archived')
        AND (read_at < ? OR (read_at IS NULL AND created_at < ?))
        """,
        (cutoff, cutoff),
    )
    conn.commit()
    return cursor.rowcount


# --- Legacy aliases for existing code ---


def add_notification(
    channel: str,
    message: str,
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
    upsert: bool = True,
) -> int:
    """Legacy wrapper - prefer using add() with connect() context manager."""
    if conn is not None:
        return add(conn, channel, message, name, metadata, upsert).id

    with connect() as conn:
        return add(conn, channel, message, name, metadata, upsert).id
