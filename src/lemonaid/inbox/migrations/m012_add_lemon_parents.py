"""Parent links between lemons, by stable Lemon-ID."""

import sqlite3

VERSION = 12
DESCRIPTION = "Add lemon parent links"


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS lemon_parents ("
        " lemon_id TEXT PRIMARY KEY, parent_id TEXT NOT NULL, linked_at REAL NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lemon_parents_parent ON lemon_parents(parent_id)")
