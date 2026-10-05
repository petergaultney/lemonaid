"""Move a brief's manual inbox state and reclaim it on backend resume."""

import json
import sqlite3
import time

from ..inbox import db
from . import handoff_state


def _move_manual_state(conn: sqlite3.Connection, source: str, target: str) -> None:
    old = db.get_by_channel(conn, source, unread_only=False)
    new = db.get_by_channel(conn, target, unread_only=False)
    if old is None or new is None:
        raise ValueError("Both backend channels need inbox rows")

    if "auto_name" in old.metadata:
        metadata = dict(new.metadata)
        metadata["auto_name"] = new.name or ""
        conn.execute(
            "UPDATE notifications SET name = ?, metadata = ? WHERE channel = ?",
            (old.name, json.dumps(metadata), target),
        )
    elif db.is_backend_name(old.metadata.get("name_source")) and not db.is_backend_name(
        new.metadata.get("name_source")
    ):
        metadata = dict(new.metadata)
        metadata["name_source"] = old.metadata["name_source"]
        conn.execute(
            "UPDATE notifications SET name = ?, metadata = ? WHERE channel = ?",
            (old.name, json.dumps(metadata), target),
        )
    conn.execute("DELETE FROM pins WHERE channel = ?", (target,))
    conn.execute("UPDATE pins SET channel = ? WHERE channel = ?", (target, source))
    conn.execute("DELETE FROM session_emoji WHERE channel = ?", (target,))
    conn.execute("UPDATE session_emoji SET channel = ? WHERE channel = ?", (target, source))
    if old.status == "snoozed" and old.snooze_until and old.snooze_until > time.time():
        conn.execute(
            """UPDATE notifications SET status = 'snoozed', snooze_until = ?,
               snooze_prev_status = ?, snooze_through_turns = ? WHERE channel = ?""",
            (old.snooze_until, old.snooze_prev_status, old.snooze_through_turns, target),
        )


def transfer(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = handoff_state.get(conn, token)
        if row["phase"] in ("transferred", "complete"):
            conn.commit()
            return

        if not row["ready"] or not row["accepted"] or not handoff_state.ready(conn, row)[0]:
            raise ValueError("Both readiness checks are required")

        holder = conn.execute(
            "SELECT channel FROM session_briefs WHERE path = ?", (row["path"],)
        ).fetchone()
        if holder is None or holder["channel"] != row["source"]:
            raise ValueError("The outgoing channel no longer holds this brief")

        _move_manual_state(conn, row["source"], row["target"])
        conn.execute("DELETE FROM session_briefs WHERE channel = ?", (row["target"],))
        conn.execute(
            "UPDATE session_briefs SET channel = ?, attached_at = ? WHERE path = ?",
            (row["target"], time.time(), row["path"]),
        )
        conn.execute(
            "UPDATE notifications SET status = 'archived' WHERE channel = ?", (row["source"],)
        )
        generation = conn.execute(
            "SELECT COALESCE(MAX(generation), 0) FROM brief_handoff_sessions WHERE path = ?",
            (row["path"],),
        ).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO brief_handoff_sessions VALUES (?, ?, ?)",
            (row["path"], row["source"], generation),
        )
        conn.execute(
            "INSERT OR REPLACE INTO brief_handoff_sessions VALUES (?, ?, ?)",
            (row["path"], row["target"], generation + 1),
        )
        conn.execute("UPDATE brief_handoffs SET phase = 'transferred' WHERE token = ?", (token,))
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def reclaim(conn: sqlite3.Connection, channel: str) -> bool:
    known = conn.execute(
        "SELECT path FROM brief_handoff_sessions WHERE channel = ?", (channel,)
    ).fetchone()
    if known is None:
        return False

    holder = conn.execute(
        "SELECT channel FROM session_briefs WHERE path = ?", (known["path"],)
    ).fetchone()
    if holder is None or holder["channel"] == channel:
        return False

    linked = conn.execute(
        "SELECT 1 FROM brief_handoff_sessions WHERE path = ? AND channel = ?",
        (known["path"], holder["channel"]),
    ).fetchone()
    if linked is None:
        return False

    conn.execute("BEGIN IMMEDIATE")
    try:
        _move_manual_state(conn, holder["channel"], channel)
        conn.execute("DELETE FROM session_briefs WHERE channel = ?", (channel,))
        conn.execute(
            "UPDATE session_briefs SET channel = ?, attached_at = ? WHERE path = ?",
            (channel, time.time(), known["path"]),
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise

    return True
