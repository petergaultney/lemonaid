"""Whether the inbox shows a group collapsed to its header line."""

import sqlite3

VERSION = 23
DESCRIPTION = "Add collapsed to lemon groups"


def migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(lemon_groups)")}
    if "collapsed" not in columns:
        conn.execute("ALTER TABLE lemon_groups ADD COLUMN collapsed INTEGER NOT NULL DEFAULT 0")
