"""Whether waiting briefs are worth another tmux lookup.

The inbox claims pending briefs on every refresh tick, and following a pending
window costs a `tmux list-windows`. Between ticks, nothing a claim depends on
usually changes: no lemon started, came back from the archive, or recorded a new
window. A recheck every `_RECHECK_SECONDS` still catches what only tmux knows,
such as a window renumbered under a lemon that was already there.
"""

import sqlite3

_RECHECK_SECONDS = 30.0

_last_checked: dict[str, tuple[list[tuple], float]] = {}  # database file -> (inputs, when)


def _inputs(conn: sqlite3.Connection) -> list[tuple]:
    return [
        *conn.execute(
            "SELECT id, channel, status, json_extract(metadata, '$.tmux_session'), "
            "json_extract(metadata, '$.tmux_window') FROM notifications "
            "WHERE status != 'archived' ORDER BY id"
        ).fetchall(),
        *conn.execute("SELECT * FROM pending_briefs ORDER BY path").fetchall(),
        *conn.execute("SELECT channel, path FROM session_briefs ORDER BY channel").fetchall(),
    ]


def due(conn: sqlite3.Connection, now: float) -> bool:
    """True when a claim could go differently than it did at the last check that was due."""
    database = conn.execute("PRAGMA database_list").fetchone()[2]
    inputs = [tuple(row) for row in _inputs(conn)]
    last = _last_checked.get(database)
    if last and last[0] == inputs and now - last[1] < _RECHECK_SECONDS:
        return False

    _last_checked[database] = (inputs, now)
    return True
