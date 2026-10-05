"""Remember the pane process being replaced so recovery cannot kill a stranger."""

import sqlite3

VERSION = 21
DESCRIPTION = "Track handoff pane processes and original exit behavior"


def migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(brief_handoffs)")}
    for name, kind in (
        ("source_pid", "TEXT NOT NULL DEFAULT ''"),
        ("target_pid", "TEXT NOT NULL DEFAULT ''"),
        ("remain_on_exit", "TEXT NOT NULL DEFAULT ''"),
        ("resume_line", "TEXT NOT NULL DEFAULT ''"),
        ("resume_cwd", "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in columns:
            conn.execute(f"ALTER TABLE brief_handoffs ADD COLUMN {name} {kind}")
