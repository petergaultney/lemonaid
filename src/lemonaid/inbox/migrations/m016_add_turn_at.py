"""Record when a session's transcript last showed a turn in progress.

The watcher sets it from the transcript's newest entry while a turn is open,
and clears it when the turn ends. NULL for a session between turns.
"""

import sqlite3

VERSION = 16
DESCRIPTION = "Add turn_at column"


def migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(notifications)")}
    if "turn_at" in columns:
        return

    conn.execute("ALTER TABLE notifications ADD COLUMN turn_at REAL")
