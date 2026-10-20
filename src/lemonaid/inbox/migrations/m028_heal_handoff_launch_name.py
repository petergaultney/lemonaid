"""Add `brief_handoffs.launch_name` to databases whose version 27 was a different migration."""

import sqlite3

VERSION = 28
DESCRIPTION = "Heal missing brief_handoffs.launch_name"


def migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(brief_handoffs)")}
    if "launch_name" not in columns:
        conn.execute("ALTER TABLE brief_handoffs ADD COLUMN launch_name TEXT NOT NULL DEFAULT ''")
