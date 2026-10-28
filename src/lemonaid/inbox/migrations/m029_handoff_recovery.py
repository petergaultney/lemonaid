"""Record explicit durable-context recovery separately from cooperative readiness."""

import sqlite3

VERSION = 29
DESCRIPTION = "Add confirmed handoff recovery snapshots"


def migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(brief_handoffs)")}
    if "recovery_hash" not in columns:
        conn.execute("ALTER TABLE brief_handoffs ADD COLUMN recovery_hash TEXT NOT NULL DEFAULT ''")
