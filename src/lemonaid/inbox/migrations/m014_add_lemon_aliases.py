"""Old Lemon-IDs a lemon had before a reroll, so messages sent to them still arrive."""

import sqlite3

VERSION = 14
DESCRIPTION = "Add Lemon-ID aliases"


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS lemon_aliases (old_id TEXT PRIMARY KEY, lemon_id TEXT NOT NULL)"
    )
