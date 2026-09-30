"""Mark a snooze that lasts through its session's turn ends.

`inbox snooze` sets it: a lemon snoozing its own row is mid-turn, so the end of
that turn would otherwise wake the snooze at once. The TUI's snoozes leave it 0.
"""

import sqlite3

VERSION = 15
DESCRIPTION = "Add snooze_through_turns column"


def migrate(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(notifications)")}
    if "snooze_through_turns" in columns:
        return

    conn.execute(
        "ALTER TABLE notifications ADD COLUMN snooze_through_turns INTEGER NOT NULL DEFAULT 0"
    )
