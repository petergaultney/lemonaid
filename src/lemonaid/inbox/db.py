"""SQLite database for lemonaid notifications."""

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self


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
    snooze_until: float | None = None
    snooze_prev_status: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Self:
        """Create a Notification from a database row."""
        # Handle columns which may not exist in older DBs
        switch_source = None
        name = None
        snooze_until = None
        snooze_prev_status = None
        with suppress(IndexError, KeyError):
            switch_source = row["switch_source"]
        with suppress(IndexError, KeyError):
            name = row["name"]
        with suppress(IndexError, KeyError):
            snooze_until = row["snooze_until"]
        with suppress(IndexError, KeyError):
            snooze_prev_status = row["snooze_prev_status"]

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
            snooze_until=snooze_until,
            snooze_prev_status=snooze_prev_status,
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

    @property
    def is_snoozed(self) -> bool:
        return self.status == "snoozed"


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


_HIDDEN_STATUSES = ("archived", "snoozed")


def get_active(conn: sqlite3.Connection, switch_source: str | None = None) -> list[Notification]:
    """Get active sessions (one per channel), unread first then by recency.

    Returns only the most recent notification per channel, excluding archived
    and snoozed ones. If switch_source is provided, filters to only
    notifications with that exact source.

    Callers that render the inbox should call wake_expired() first; this query
    does not itself resurrect sessions whose snooze has run out.
    """
    if switch_source:
        rows = conn.execute(
            """
            SELECT n.* FROM notifications n
            INNER JOIN (
                SELECT channel, MAX(id) as max_id
                FROM notifications
                WHERE status NOT IN ('archived', 'snoozed')
                GROUP BY channel
            ) latest ON n.id = latest.max_id
            WHERE n.status NOT IN ('archived', 'snoozed')
            AND n.switch_source = ?
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
                WHERE status NOT IN ('archived', 'snoozed')
                GROUP BY channel
            ) latest ON n.id = latest.max_id
            WHERE n.status NOT IN ('archived', 'snoozed')
            ORDER BY
                CASE n.status WHEN 'unread' THEN 0 ELSE 1 END,
                n.created_at DESC
            """
        ).fetchall()
    return [Notification.from_row(row) for row in rows]


def get_snoozed(conn: sqlite3.Connection) -> list[Notification]:
    """Get snoozed sessions, soonest to wake first."""
    rows = conn.execute(
        """
        SELECT n.* FROM notifications n
        INNER JOIN (
            SELECT channel, MAX(id) as max_id
            FROM notifications
            WHERE status = 'snoozed'
            GROUP BY channel
        ) latest ON n.id = latest.max_id
        WHERE n.status = 'snoozed'
        ORDER BY n.snooze_until ASC
        """
    ).fetchall()
    return [Notification.from_row(row) for row in rows]


def get_history(
    conn: sqlite3.Connection,
    limit: int = 200,
    search: str = "",
) -> list[Notification]:
    """Get resumable sessions for the history view, newest first.

    Includes archived/read sessions plus headless sessions (switch_source IS NULL)
    regardless of status — headless sessions have no tmux/wezterm to switch to,
    so they're only reachable via history. Optionally filters by substring match
    on name, message, channel, cwd, or git_branch. Returns only the most recent
    notification per channel.
    """
    status_cond = (
        "n.status != 'snoozed' AND (n.status IN ('archived', 'read') OR n.switch_source IS NULL)"
    )
    latest_cond = (
        "status != 'snoozed' AND (status IN ('archived', 'read') OR switch_source IS NULL)"
    )
    if search:
        pattern = f"%{search}%"
        rows = conn.execute(
            f"""
            SELECT n.* FROM notifications n
            INNER JOIN (
                SELECT channel, MAX(id) as max_id
                FROM notifications
                WHERE {latest_cond}
                GROUP BY channel
            ) latest ON n.id = latest.max_id
            WHERE {status_cond}
            AND (
                n.name LIKE ?
                OR n.message LIKE ?
                OR n.channel LIKE ?
                OR json_extract(n.metadata, '$.cwd') LIKE ?
                OR json_extract(n.metadata, '$.git_branch') LIKE ?
            )
            ORDER BY n.created_at DESC
            LIMIT ?
            """,
            (pattern, pattern, pattern, pattern, pattern, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT n.* FROM notifications n
            INNER JOIN (
                SELECT channel, MAX(id) as max_id
                FROM notifications
                WHERE {latest_cond}
                GROUP BY channel
            ) latest ON n.id = latest.max_id
            WHERE {status_cond}
            ORDER BY n.created_at DESC
            LIMIT ?
            """,
            (limit,),
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


def _is_backend_name(name_source: Any) -> bool:
    """Whether a name_source denotes a real backend title rather than a placeholder.

    Placeholders come from the environment (tmux session, cwd). Backend titles
    come from the agent itself — an AI-generated title or a user's /rename.
    """
    return bool(name_source) and name_source != "environment"


def _reconcile_name(
    existing: Notification,
    name: str | None,
    metadata: dict[str, Any],
) -> str | None:
    """Decide the name to store when re-observing a known session.

    A user rename always wins and is never overwritten. Otherwise the incoming
    name replaces the stored one, which lets a placeholder derived from tmux or
    cwd be upgraded once the backend produces a real title. `metadata` is
    mutated to carry forward the preserved rename bookkeeping.
    """
    if "auto_name" in existing.metadata:
        # The user renamed this session; keep their name. The stored auto-name is
        # only upgraded by a real backend title, so clearing the override later
        # restores a good name rather than whatever tmux happened to be called.
        if name and _is_backend_name(metadata.get("name_source")):
            metadata["auto_name"] = name
        else:
            metadata["auto_name"] = existing.metadata["auto_name"]
        return existing.name

    if not name:
        return existing.name

    if not _is_backend_name(metadata.get("name_source")) and _is_backend_name(
        existing.metadata.get("name_source")
    ):
        # Don't regress a real backend title back to a tmux/cwd placeholder.
        metadata["name_source"] = existing.metadata["name_source"]
        return existing.name

    return name


def add(
    conn: sqlite3.Connection,
    channel: str,
    message: str,
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
    upsert: bool = True,
    switch_source: str | None = None,
    created_at: float | None = None,
    status: str = "unread",
) -> Notification:
    """Add a notification or update existing one if upsert=True.

    If upsert=True and a notification exists for the channel (even if read or archived),
    it will be updated and set back to unread status.
    """
    now = created_at if created_at is not None else time.time()
    metadata = metadata or {}

    if upsert:
        # Look for any existing notification for this channel (including read/archived)
        existing = get_by_channel(conn, channel, unread_only=False)
        if existing:
            name = _reconcile_name(existing, name, metadata)

            conn.execute(
                """
                UPDATE notifications
                SET message = ?, name = ?, metadata = ?, created_at = ?, status = 'unread', read_at = NULL, switch_source = ?,
                    snooze_until = NULL, snooze_prev_status = NULL
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
        INSERT INTO notifications (channel, message, name, metadata, created_at, switch_source, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (channel, message, name, json.dumps(metadata), now, switch_source, status),
    )
    conn.commit()

    return Notification(
        id=cursor.lastrowid or 0,
        channel=channel,
        message=message,
        name=name,
        metadata=metadata,
        status=status,
        created_at=now,
        switch_source=switch_source,
    )


def register_working(
    conn: sqlite3.Connection,
    channel: str,
    message: str,
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
    switch_source: str | None = None,
) -> Notification:
    """Register a session that has started working (e.g. on prompt submit).

    Unlike add(), this never flags the session for attention: a brand-new
    session is inserted as 'read', and an existing session keeps its current
    status (so a session already 'unread' from a Stop/Notification hook is not
    silently dismissed, and a 'read' working session is not re-flagged).

    created_at is the session's birth time and is never overwritten on update,
    so actively-driven sessions hold a stable position rather than churning to
    the top of the active list on every turn. An archived session reappears as
    'read' (you're driving it again) but keeps its original created_at.
    """
    metadata = metadata or {}
    existing = get_by_channel(conn, channel, unread_only=False)

    if existing:
        name = _reconcile_name(existing, name, metadata)

        new_status = "read" if existing.is_archived else existing.status
        conn.execute(
            """
            UPDATE notifications
            SET message = ?, name = ?, metadata = ?, switch_source = ?, status = ?
            WHERE id = ?
            """,
            (message, name, json.dumps(metadata), switch_source, new_status, existing.id),
        )
        conn.commit()
        return Notification(
            id=existing.id,
            channel=channel,
            message=message,
            name=name,
            metadata=metadata,
            status=new_status,
            created_at=existing.created_at,
            switch_source=switch_source,
        )

    now = time.time()
    cursor = conn.execute(
        """
        INSERT INTO notifications (channel, message, name, metadata, created_at, switch_source, status)
        VALUES (?, ?, ?, ?, ?, ?, 'read')
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
        status="read",
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


def mark_unread(conn: sqlite3.Connection, notification_id: int) -> None:
    """Return a session to the inbox's unread group at its existing age.

    Unlike mark_unread_for_channel(), created_at is left alone: this says "I have
    not dealt with this yet", not "this just spoke", so the session sorts among
    the unreads where its age puts it rather than jumping to the top.
    """
    conn.execute(
        "UPDATE notifications SET status = 'unread', read_at = NULL WHERE id = ?",
        (notification_id,),
    )
    conn.commit()


def mark_unread_for_channel(conn: sqlite3.Connection, channel: str) -> int:
    """Mark all notifications for a channel as unread (needs attention).

    Used when an agent finishes and is waiting for user input.
    Also updates created_at to now, so that should_dismiss() only looks
    at entries after this point (prevents flip-flopping).

    This cancels an active snooze: fresh output means the session wants the user
    again, and a snooze only defers the state it was applied to.
    Returns count of notifications marked as unread.
    """
    now = time.time()
    cursor = conn.execute(
        """
        UPDATE notifications
        SET status = 'unread', read_at = NULL, created_at = ?,
            snooze_until = NULL, snooze_prev_status = NULL
        WHERE channel = ? AND status IN ('read', 'snoozed')
        """,
        (now, channel),
    )
    conn.commit()
    return cursor.rowcount


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
    extra_metadata: dict[str, Any] | None = None,
) -> bool:
    """Update (or clear) the user-override name for a notification.

    When setting a name, preserves the current auto-detected name in metadata.
    When clearing (name=None), restores the auto-detected name if available.
    If extra_metadata is provided, those keys are merged into metadata.

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

    if extra_metadata:
        metadata.update(extra_metadata)

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


def refresh_auto_name(
    conn: sqlite3.Connection,
    notification_id: int,
    name: str,
    name_source: str,
) -> bool:
    """Apply a freshly-discovered backend title to a session.

    Backends name a session only after it has run for a while, so the inbox
    holds a placeholder until then. This upgrades that placeholder without
    disturbing a name the user set inside lemonaid, which stays visible while its
    stored auto-name is brought up to date. Returns True if anything changed.
    """
    notification = get(conn, notification_id)
    if not notification or not name:
        return False

    metadata = dict(notification.metadata)
    renamed = "auto_name" in metadata

    if renamed:
        if metadata["auto_name"] == name and metadata.get("name_source") == name_source:
            return False
        metadata["auto_name"] = name
        final_name = notification.name
    else:
        if notification.name == name and metadata.get("name_source") == name_source:
            return False
        final_name = name

    metadata["name_source"] = name_source
    conn.execute(
        "UPDATE notifications SET name = ?, metadata = ? WHERE channel = ?",
        (final_name, json.dumps(metadata), notification.channel),
    )
    conn.commit()
    return True


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
    """Archive a notification and all other rows sharing its channel."""
    row = conn.execute(
        "SELECT channel FROM notifications WHERE id = ?", (notification_id,)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE notifications SET status = 'archived' WHERE channel = ?",
            (row["channel"],),
        )
    else:
        conn.execute(
            "UPDATE notifications SET status = 'archived' WHERE id = ?",
            (notification_id,),
        )
    conn.commit()


def snooze(conn: sqlite3.Connection, notification_id: int, until: float) -> None:
    """Hold a session out of the inbox until `until`, then return it as unread.

    Applies to every row on the channel, matching archive()'s scope. The current
    status is recorded so wake_expired() can tell whether the session was
    demanding attention when it was snoozed.
    """
    row = conn.execute(
        "SELECT channel, status FROM notifications WHERE id = ?", (notification_id,)
    ).fetchone()
    if not row:
        return

    conn.execute(
        """
        UPDATE notifications
        SET status = 'snoozed', snooze_until = ?, snooze_prev_status = status
        WHERE channel = ? AND status != 'snoozed'
        """,
        (until, row["channel"]),
    )
    conn.commit()


def unsnooze(conn: sqlite3.Connection, channel: str) -> int:
    """Return a snoozed channel to the inbox, restoring its pre-snooze status.

    Used both by the expiry sweep and by an explicit un-snooze. Returns the
    number of rows woken.
    """
    cursor = conn.execute(
        """
        UPDATE notifications
        SET status = COALESCE(snooze_prev_status, 'unread'),
            snooze_until = NULL,
            snooze_prev_status = NULL
        WHERE channel = ? AND status = 'snoozed'
        """,
        (channel,),
    )
    conn.commit()
    return cursor.rowcount


def wake_expired(conn: sqlite3.Connection, now: float | None = None) -> list[str]:
    """Wake every snoozed session whose timer has passed. Returns woken channels.

    A session that was unread when snoozed comes back unread; one that was
    merely read comes back read, so snoozing a quiet session doesn't manufacture
    a notification out of nothing.
    """
    now = now if now is not None else time.time()
    channels = [
        row["channel"]
        for row in conn.execute(
            "SELECT DISTINCT channel FROM notifications WHERE status = 'snoozed' AND snooze_until <= ?",
            (now,),
        ).fetchall()
    ]
    for channel in channels:
        unsnooze(conn, channel)

    return channels


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
