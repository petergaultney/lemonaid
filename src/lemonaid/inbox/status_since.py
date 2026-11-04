"""When a brief entered its current Status, and its current Needs.

A brief's mtime moves with every bullet edit, so it can't say how long a lemon
has been `waiting`. Lemonaid records the time it first sees each Status (and,
separately, each Needs) instead, taken from the file's mtime at that moment: the
edit that changed it is the newest one seen. A record changes only when its
value does.
"""

import sqlite3
import typing as ty
from collections import abc
from pathlib import Path


def _observe(
    conn: sqlite3.Connection,
    table: ty.Literal["brief_status_since", "brief_needs_since"],
    column: ty.Literal["status", "needs"],
    values: abc.Mapping[Path, tuple[str, float]],
) -> dict[Path, float]:
    if not values:
        return {}

    keys = [str(path) for path in values]
    recorded = {
        row[0]: (row[1], row[2])
        for row in conn.execute(
            f"SELECT path, {column}, since FROM {table}"
            f" WHERE path IN ({','.join('?' * len(keys))})",
            keys,
        )
    }
    changed = {
        str(path): (value, mtime)
        for path, (value, mtime) in values.items()
        if str(path) not in recorded or recorded[str(path)][0] != value
    }
    if changed:
        conn.executemany(
            f"INSERT OR REPLACE INTO {table} (path, {column}, since) VALUES (?, ?, ?)",
            [(path, value, mtime) for path, (value, mtime) in changed.items()],
        )
        conn.commit()

    return {path: (changed.get(str(path)) or recorded[str(path)])[1] for path in values}


def observe(
    conn: sqlite3.Connection, statuses: abc.Mapping[Path, tuple[str, float]]
) -> dict[Path, float]:
    """When each brief entered its Status, from *statuses* of (status, mtime) by path.

    Records a brief whose Status is new, or that has no record yet.
    """
    return _observe(conn, "brief_status_since", "status", statuses)


def observe_needs(
    conn: sqlite3.Connection, needs: abc.Mapping[Path, tuple[str, float]]
) -> dict[Path, float]:
    """When each brief's Needs took its current text, from *needs* of (text, mtime) by path."""
    return _observe(conn, "brief_needs_since", "needs", needs)
