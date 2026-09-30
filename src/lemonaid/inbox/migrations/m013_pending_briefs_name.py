"""A name for the lemon a waiting brief goes to, set on its session once it starts.

`lemon start --name` can't rename a session that has no inbox row yet, so the
name waits with the brief and is applied when the brief is claimed.
"""

import sqlite3

VERSION = 13
DESCRIPTION = "Add a name to pending briefs"


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE pending_briefs ADD COLUMN name TEXT NOT NULL DEFAULT ''")
