"""When a brief entered its current Status.

A brief's mtime moves with every bullet edit, so it can't say how long a lemon
has been `waiting`. The inbox records the time it first sees each Status
instead, taken from the file's mtime at that moment: the edit that changed the
Status is the newest one it has seen. The record changes only when the Status
does.
"""

import sqlite3
from collections import abc
from pathlib import Path


def observe(
    conn: sqlite3.Connection, statuses: abc.Mapping[Path, tuple[str, float]]
) -> dict[Path, float]:
    """When each brief entered its Status, from *statuses* of (status, mtime) by path.

    Records a brief whose Status is new, or that has no record yet.
    """
    if not statuses:
        return {}

    keys = [str(path) for path in statuses]
    recorded = {
        row[0]: (row[1], row[2])
        for row in conn.execute(
            f"SELECT path, status, since FROM brief_status_since"
            f" WHERE path IN ({','.join('?' * len(keys))})",
            keys,
        )
    }
    changed = {
        str(path): (state, mtime)
        for path, (state, mtime) in statuses.items()
        if recorded.get(str(path), ("", 0.0))[0] != state
    }
    if changed:
        conn.executemany(
            "INSERT OR REPLACE INTO brief_status_since (path, status, since) VALUES (?, ?, ?)",
            [(path, state, mtime) for path, (state, mtime) in changed.items()],
        )
        conn.commit()

    return {path: (changed.get(str(path)) or recorded[str(path)])[1] for path in statuses}
