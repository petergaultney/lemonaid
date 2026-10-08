"""Explicit terminal teardown requests, valid only for their recorded location."""

import json
import sqlite3
from collections import abc

from . import db

_LOCATION_KEYS = ("tty", "tmux_socket", "tmux_session_order", "tmux_pane_identity")


def _location(row: db.Notification) -> dict[str, object]:
    return {key: row.metadata.get(key) for key in _LOCATION_KEYS}


def applies(row: db.Notification) -> bool:
    evidence = row.metadata.get("place_teardown")
    return bool(evidence) and evidence == _location(row)


def record(conn: sqlite3.Connection, rows: abc.Iterable[db.Notification]) -> None:
    for selected in rows:
        row = db.get(conn, selected.id)
        if row is None or row.is_archived or _location(row) != _location(selected):
            continue

        conn.execute(
            "UPDATE notifications SET metadata = ? WHERE id = ?",
            (json.dumps({**row.metadata, "place_teardown": _location(row)}), row.id),
        )
    conn.commit()
