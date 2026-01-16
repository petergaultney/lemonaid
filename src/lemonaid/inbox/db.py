"""SQLite database for lemonaid notifications."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


def get_db_path() -> Path:
    """Get the path to the lemonaid database, following XDG conventions."""
    xdg_data = Path.home() / ".local" / "share"
    lemonaid_dir = xdg_data / "lemonaid"
    lemonaid_dir.mkdir(parents=True, exist_ok=True)
    return lemonaid_dir / "lemonaid.db"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a database connection, creating the schema if needed."""
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    """Initialize the database schema."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,           -- e.g., "claude:session_id" or tool identifier
            title TEXT NOT NULL,             -- short display title
            message TEXT,                    -- optional longer message
            metadata TEXT,                   -- JSON blob for handler-specific data
            status TEXT DEFAULT 'unread',    -- 'unread' or 'read'
            created_at REAL NOT NULL,        -- unix timestamp
            read_at REAL                     -- unix timestamp when marked read
        );

        CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
        CREATE INDEX IF NOT EXISTS idx_notifications_channel ON notifications(channel);
        CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);
    """)
    conn.commit()


def add_notification(
    channel: str,
    title: str,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Add a new notification. Returns the notification ID."""
    close_conn = conn is None
    if conn is None:
        conn = get_connection()

    try:
        cursor = conn.execute(
            """
            INSERT INTO notifications (channel, title, message, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                channel,
                title,
                message,
                json.dumps(metadata) if metadata else None,
                time.time(),
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0
    finally:
        if close_conn:
            conn.close()


def get_unread(conn: sqlite3.Connection | None = None) -> list[sqlite3.Row]:
    """Get all unread notifications, newest first."""
    close_conn = conn is None
    if conn is None:
        conn = get_connection()

    try:
        return conn.execute(
            """
            SELECT * FROM notifications
            WHERE status = 'unread'
            ORDER BY created_at DESC
            """
        ).fetchall()
    finally:
        if close_conn:
            conn.close()


def mark_read(notification_id: int, conn: sqlite3.Connection | None = None) -> None:
    """Mark a notification as read."""
    close_conn = conn is None
    if conn is None:
        conn = get_connection()

    try:
        conn.execute(
            """
            UPDATE notifications
            SET status = 'read', read_at = ?
            WHERE id = ?
            """,
            (time.time(), notification_id),
        )
        conn.commit()
    finally:
        if close_conn:
            conn.close()


def mark_all_read_for_channel(channel: str, conn: sqlite3.Connection | None = None) -> int:
    """Mark all notifications for a channel as read. Returns count updated."""
    close_conn = conn is None
    if conn is None:
        conn = get_connection()

    try:
        cursor = conn.execute(
            """
            UPDATE notifications
            SET status = 'read', read_at = ?
            WHERE channel = ? AND status = 'unread'
            """,
            (time.time(), channel),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        if close_conn:
            conn.close()


def clear_old_notifications(days: int = 7, conn: sqlite3.Connection | None = None) -> int:
    """Delete read notifications older than N days. Returns count deleted."""
    close_conn = conn is None
    if conn is None:
        conn = get_connection()

    try:
        cutoff = time.time() - (days * 24 * 60 * 60)
        cursor = conn.execute(
            """
            DELETE FROM notifications
            WHERE status = 'read' AND read_at < ?
            """,
            (cutoff,),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        if close_conn:
            conn.close()
