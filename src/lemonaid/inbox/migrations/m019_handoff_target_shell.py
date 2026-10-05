"""Remember the shell in a reserved handoff pane for launch retries."""

import sqlite3

VERSION = 19
DESCRIPTION = "Remember the handoff target shell"


def migrate(conn: sqlite3.Connection) -> None:
    if "target_shell" in {row[1] for row in conn.execute("PRAGMA table_info(brief_handoffs)")}:
        return

    conn.execute("ALTER TABLE brief_handoffs ADD COLUMN target_shell TEXT NOT NULL DEFAULT ''")
