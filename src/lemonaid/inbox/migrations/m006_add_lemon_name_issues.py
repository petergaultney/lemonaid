"""Keep every issued lemon name, including retired place assignments."""

import sqlite3

VERSION = 6
DESCRIPTION = "Add lemon name issue history"


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS lemon_name_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            directory TEXT NOT NULL,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            issued_at REAL NOT NULL,
            retired_at REAL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_lemon_name_active_directory
        ON lemon_name_issues(directory)
        WHERE retired_at IS NULL;
    """)
