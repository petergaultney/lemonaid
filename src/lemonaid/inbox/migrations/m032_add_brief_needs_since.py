"""When each brief's current Needs began, as lemonaid first saw it."""

import sqlite3

VERSION = 32
DESCRIPTION = "Add brief_needs_since table"


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS brief_needs_since ("
        " path TEXT PRIMARY KEY, needs TEXT NOT NULL, since REAL NOT NULL)"
    )
