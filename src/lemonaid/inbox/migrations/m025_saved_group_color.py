"""A group's color as set from lemonaid, first stored in a `colour` column.

Databases that ran the old migration 24 already have the column, holding
colors an earlier release assigned automatically; those are cleared so every
group starts with none saved. Migration 26 renames the column `color`.
"""

import sqlite3

VERSION = 25
DESCRIPTION = "Add a saved colour to lemon groups"


def migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(lemon_groups)")}
    if "colour" in columns:
        conn.execute("UPDATE lemon_groups SET colour = ''")
    else:
        conn.execute("ALTER TABLE lemon_groups ADD COLUMN colour TEXT NOT NULL DEFAULT ''")
