"""Keep the outgoing pane's command for safe handoff teardown."""

import sqlite3

VERSION = 20
DESCRIPTION = "Remember the handoff source command"


def migrate(conn: sqlite3.Connection) -> None:
    if "source_command" in {row[1] for row in conn.execute("PRAGMA table_info(brief_handoffs)")}:
        return

    conn.execute("ALTER TABLE brief_handoffs ADD COLUMN source_command TEXT NOT NULL DEFAULT ''")
