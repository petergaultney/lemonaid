"""When each brief's current Status began, as the inbox first saw it."""

import sqlite3

VERSION = 17
DESCRIPTION = "Add brief_status_since table"


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS brief_status_since ("
        " path TEXT PRIMARY KEY, status TEXT NOT NULL, since REAL NOT NULL)"
    )
