"""Briefs attached to harness sessions, and attachments waiting for a lemon.

VERSION 6 and 7 belong to lemon-name issues and session emoji, which some
databases already carry from before those branches merged; this one follows
them so it runs on those databases too.
"""

import sqlite3

VERSION = 8
DESCRIPTION = "Add session briefs"


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS session_briefs (
            channel TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            attached_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pending_briefs (
            tmux_session TEXT NOT NULL,
            tmux_window TEXT NOT NULL,
            path TEXT NOT NULL,
            after_id INTEGER NOT NULL,
            requested_at REAL NOT NULL,
            PRIMARY KEY (tmux_session, tmux_window)
        );
    """)
