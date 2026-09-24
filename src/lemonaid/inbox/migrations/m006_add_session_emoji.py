"""Per-session emoji, shown before the session's name."""

import sqlite3

VERSION = 6
DESCRIPTION = "Add session emoji"


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS session_emoji (
            channel TEXT PRIMARY KEY,
            emoji TEXT NOT NULL,
            set_at REAL NOT NULL
        );
    """)
