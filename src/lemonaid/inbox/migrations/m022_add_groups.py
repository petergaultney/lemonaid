"""Named groups of lemons, with members recorded by stable Lemon-ID.

A group has an integer id so a rename touches one row. `position` is REAL,
like a pin's, so the inbox can order groups and later insert between two.
"""

import sqlite3

VERSION = 22
DESCRIPTION = "Add lemon groups"


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS lemon_groups ("
        " group_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, position REAL NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS lemon_group_members ("
        " group_id INTEGER NOT NULL,"
        " lemon_id TEXT NOT NULL, added_at REAL NOT NULL, PRIMARY KEY (group_id, lemon_id))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lemon_group_members_lemon ON lemon_group_members(lemon_id)"
    )
