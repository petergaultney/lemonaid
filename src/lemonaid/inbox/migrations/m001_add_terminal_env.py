"""Add terminal_env column to notifications table.

This allows filtering notifications by the terminal environment
(tmux, wezterm, etc.) they originated from.
"""

import sqlite3

VERSION = 1
DESCRIPTION = "Add terminal_env column to notifications"


def migrate(conn: sqlite3.Connection) -> None:
    """Add terminal_env column with NULL default for existing rows."""
    conn.execute("ALTER TABLE notifications ADD COLUMN terminal_env TEXT")
