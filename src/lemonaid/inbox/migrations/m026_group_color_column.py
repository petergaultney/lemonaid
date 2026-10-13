"""Rename a group's saved `colour` column to `color`, keeping the colors saved in it.

A database whose migration 25 already made `color` is left as it is.
"""

import sqlite3

VERSION = 26
DESCRIPTION = "Rename lemon groups' colour column to color"


def migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(lemon_groups)")}
    if "color" not in columns:
        conn.execute("ALTER TABLE lemon_groups RENAME COLUMN colour TO color")
