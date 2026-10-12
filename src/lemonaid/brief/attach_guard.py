"""Refuse to take a brief that another live session holds."""

import sqlite3
from pathlib import Path

from ..inbox import db
from ..messages import recipient
from ..messages import store as inbox_store


def refusal(conn: sqlite3.Connection, channel: str, path: Path, lemon_id: str) -> str:
    """Why *channel* may not take *path* from its current holder, or "" if it may.

    A holder whose harness has exited (`dead`) can always be replaced; any other
    holder, including a `deaf` one, is a session that is still running.
    """
    holder = conn.execute(
        "SELECT channel FROM session_briefs WHERE path = ? AND channel != ?", (str(path), channel)
    ).fetchone()
    if holder is None:
        return ""

    found = db.get_by_channel(conn, holder["channel"], unread_only=False)
    state = recipient.probe(holder["channel"], found, inbox_store.inbox_for_id(lemon_id))
    if state.state == recipient.DEAD:
        return ""

    return (
        f"{path.name} is held by {holder['channel']}, which is {state.state}: {state.detail}. "
        "Pass --force to take it anyway."
    )
