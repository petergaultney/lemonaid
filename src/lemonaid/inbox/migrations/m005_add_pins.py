"""Add pinned sessions.

A pin belongs to a channel rather than to a notification, so it survives the
new rows that arrive on that channel. Snooze and archive write across existing
rows and would leave a fresh notification unpinned.

`position` is REAL so a later insert-between-two-rows has somewhere to go.
Moving a pin one slot only ever swaps two values, which needs no such room, so
the values written today are integer-spaced.
"""

import sqlite3

VERSION = 5
DESCRIPTION = "Add pins table"


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pins (
            channel TEXT PRIMARY KEY,
            position REAL NOT NULL
        )
    """)
