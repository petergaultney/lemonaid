"""Rename title column to message and add name column.

- title -> message: better reflects that this is a status/event message
- old message column (unused) is dropped
- name: the session identity (e.g., Claude Code's customTitle or firstPrompt)
"""

import sqlite3

VERSION = 2
DESCRIPTION = "Rename title to message, add name column"


def migrate(conn: sqlite3.Connection) -> None:
    """Rename title column to message and add name column.

    The original schema had both 'title' (main text) and 'message' (unused optional text).
    We drop the unused 'message', rename 'title' to 'message', and add 'name'.
    """
    # SQLite 3.35+ supports DROP COLUMN, 3.25+ supports RENAME COLUMN
    conn.execute("ALTER TABLE notifications DROP COLUMN message")
    conn.execute("ALTER TABLE notifications RENAME COLUMN title TO message")
    conn.execute("ALTER TABLE notifications ADD COLUMN name TEXT")
