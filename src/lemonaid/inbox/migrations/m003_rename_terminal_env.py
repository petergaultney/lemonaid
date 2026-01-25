"""Rename terminal_env column to switch_source.

This reflects the new terminology: the switch-source determines which
switch-handler can navigate back to the notification's origin.
"""

import sqlite3

VERSION = 3
DESCRIPTION = "Rename terminal_env to switch_source"


def migrate(conn: sqlite3.Connection) -> None:
    """Rename terminal_env column to switch_source."""
    conn.execute("ALTER TABLE notifications RENAME COLUMN terminal_env TO switch_source")
