"""Track stable lemon IDs independently of channels and brief filenames."""

import sqlite3

VERSION = 9
DESCRIPTION = "Add stable lemon identities"


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE lemon_identities (path TEXT PRIMARY KEY, lemon_id TEXT NOT NULL UNIQUE)"
    )
