"""The channel each archived brief was attached to, so resuming its lemon can attach it again."""

import sqlite3

VERSION = 31
DESCRIPTION = "Add archived_channels table"


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS archived_channels"
        " (lemon_id TEXT PRIMARY KEY, channel TEXT NOT NULL)"
    )
