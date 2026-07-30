"""Add snooze support.

A snoozed session is held out of the active inbox until `snooze_until` passes,
at which point it returns as unread. The status column keeps its own value so a
waking session can be restored to what it was before the snooze.
"""

import sqlite3

VERSION = 4
DESCRIPTION = "Add snooze_until and snooze_prev_status columns"


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE notifications ADD COLUMN snooze_until REAL")
    conn.execute("ALTER TABLE notifications ADD COLUMN snooze_prev_status TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_snooze ON notifications(snooze_until)"
    )
