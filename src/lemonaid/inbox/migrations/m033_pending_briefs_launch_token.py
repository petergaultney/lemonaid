"""Let a brief wait for a lemon by the launch token in its environment, in any terminal.

A waiting brief was keyed on its tmux window, so outside tmux there was nothing
to wait on. A row now has a launch token, a tmux window, or both; each is unique
among the rows that have one.
"""

import sqlite3

VERSION = 33
DESCRIPTION = "Key pending briefs on a launch token as well as a tmux window"

_COLUMNS = (
    "tmux_session",
    "tmux_window",
    "path",
    "tmux_window_id",
    "live_before",
    "requested_at",
    "name",
)


def migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(pending_briefs)")}
    if "launch_token" in existing:
        return

    if existing:
        conn.execute("ALTER TABLE pending_briefs RENAME TO pending_briefs_by_window")
    # Separate statements: `executescript` would commit the runner's exclusive transaction.
    conn.execute("""
        CREATE TABLE pending_briefs (
            path TEXT NOT NULL,
            launch_token TEXT NOT NULL DEFAULT '',
            tmux_session TEXT NOT NULL DEFAULT '',
            tmux_window TEXT NOT NULL DEFAULT '',
            tmux_window_id TEXT NOT NULL DEFAULT '',
            live_before TEXT NOT NULL DEFAULT '[]',
            requested_at REAL NOT NULL,
            name TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute(
        "CREATE UNIQUE INDEX pending_briefs_window"
        " ON pending_briefs (tmux_session, tmux_window) WHERE tmux_session != ''"
    )
    conn.execute(
        "CREATE UNIQUE INDEX pending_briefs_launch_token"
        " ON pending_briefs (launch_token) WHERE launch_token != ''"
    )
    if not existing:
        return

    columns = ", ".join(_COLUMNS)
    conn.execute(
        f"INSERT INTO pending_briefs ({columns}) SELECT {columns} FROM pending_briefs_by_window"
    )
    conn.execute("DROP TABLE pending_briefs_by_window")
