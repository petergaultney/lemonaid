"""A Lemon-ID with what lemonaid knows about its work: brief, Status:, and channel."""

import dataclasses
import sqlite3

from .. import brief


@dataclasses.dataclass(frozen=True)
class Lemon:
    lemon_id: str
    brief: str  # "" when lemonaid knows no brief for it
    status: str
    channel: str  # "" when its brief is not attached to a running lemon


def describe(conn: sqlite3.Connection, lemon_id: str) -> Lemon:
    path = brief.lemon.brief_of(conn, lemon_id)
    if path is None or not path.is_file():
        return Lemon(lemon_id, str(path or ""), "", "")

    parts = brief.status.split(path.read_text())
    channel = conn.execute(
        "SELECT channel FROM session_briefs WHERE path = ?", (str(path),)
    ).fetchone()
    return Lemon(lemon_id, str(path), parts.status, channel["channel"] if channel else "")
