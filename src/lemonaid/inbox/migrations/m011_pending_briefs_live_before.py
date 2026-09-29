"""Wait for a lemon by which channels were live, and in a window tmux can renumber.

A resumed session keeps its old row, so a lemon revived from the archive into
the waiting window had an id below the one recorded and never got its brief.
Each pending attachment now records the channels that were live when it was
requested; a waiting row from before this keeps the ones live now with ids no
newer than it recorded. It also records tmux's window ID, when tmux knew it,
so the window is found again after its index changes.
"""

import json
import sqlite3

VERSION = 11
DESCRIPTION = "Record live channels for pending briefs"


def migrate(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT * FROM pending_briefs").fetchall()
    conn.execute("DROP TABLE pending_briefs")
    conn.execute("""
        CREATE TABLE pending_briefs (
            tmux_session TEXT NOT NULL,
            tmux_window TEXT NOT NULL,
            path TEXT NOT NULL,
            tmux_window_id TEXT NOT NULL,
            live_before TEXT NOT NULL,
            requested_at REAL NOT NULL,
            PRIMARY KEY (tmux_session, tmux_window)
        )
    """)
    for row in rows:
        live = [
            channel
            for (channel,) in conn.execute(
                "SELECT DISTINCT channel FROM notifications WHERE id <= ? AND status != 'archived'",
                (row["after_id"],),
            )
        ]
        conn.execute(
            "INSERT INTO pending_briefs VALUES (?, ?, ?, ?, ?, ?)",
            (
                row["tmux_session"],
                row["tmux_window"],
                row["path"],
                "",
                json.dumps(live),
                row["requested_at"],
            ),
        )
