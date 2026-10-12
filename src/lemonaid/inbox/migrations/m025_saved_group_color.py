"""A group's color as set from lemonaid, which outranks `[tui.group_colors]`.

Databases that ran the old migration 24 have an unused `colour` column holding
colors an earlier release assigned automatically; it is dropped, so every group
starts with none saved.
"""

import sqlite3

VERSION = 25
DESCRIPTION = "Add a saved color to lemon groups"


def migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(lemon_groups)")}
    if "colour" in columns:
        conn.execute("ALTER TABLE lemon_groups DROP COLUMN colour")
    if "color" not in columns:
        conn.execute("ALTER TABLE lemon_groups ADD COLUMN color TEXT NOT NULL DEFAULT ''")
