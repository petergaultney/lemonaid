"""Keep a handoff's named lemon separate from its backend identity."""

import sqlite3

VERSION = 27
DESCRIPTION = "Add named lemon selection to brief handoffs"


def migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(brief_handoffs)")}
    if "launch_name" not in columns:
        conn.execute("ALTER TABLE brief_handoffs ADD COLUMN launch_name TEXT NOT NULL DEFAULT ''")
