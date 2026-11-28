"""An OpenClaw lemon's inbox row when one of its turns ends."""

import re
import sqlite3
import time
from collections import abc

from .. import auto_read
from ..conversation import openclaw as conversation
from ..inbox import db
from ..log import get_logger
from . import sessions

_log = get_logger("openclaw.turn_end")


def _mark(conn: sqlite3.Connection, channel: str, status: str) -> int:
    """Set an unarchived row to *status* as of now. A snooze held through turns stays, waking
    unread if any turn it held ended unread; any other snooze ends."""
    now = time.time()
    held = "status = 'snoozed' AND snooze_through_turns AND snooze_until IS NOT NULL"
    cursor = conn.execute(
        f"""
        UPDATE notifications SET
            snooze_prev_status = CASE WHEN {held}
                THEN CASE WHEN :status = 'unread' OR snooze_prev_status = 'unread'
                    THEN 'unread' ELSE :status END END,
            snooze_until = CASE WHEN {held} THEN snooze_until END,
            snooze_through_turns = CASE WHEN {held} THEN 1 ELSE 0 END,
            read_at = CASE WHEN {held} THEN read_at WHEN :status = 'read' THEN :now END,
            status = CASE WHEN {held} THEN 'snoozed' ELSE :status END,
            created_at = :now
        WHERE channel = :channel AND status IN ('read', 'unread', 'snoozed')
        """,
        {"status": status, "now": now, "channel": channel},
    )
    conn.commit()
    return cursor.rowcount


def settle(
    session_key: str,
    cli: str,
    patterns: abc.Sequence[re.Pattern[str]],
    started: float,
    failed: bool,
) -> None:
    """Only a message the lemon wrote since *started* can match *patterns*, so a turn that
    failed before writing one isn't judged by the turn before it."""
    channel = sessions.channel(session_key)
    said = ""
    if patterns and not failed:
        try:
            said = conversation.final_message(session_key, cli, started)
        except OSError as error:
            _log.warning("can't read %s's final message: %s", session_key, error)
    with db.connect() as conn:
        _mark(conn, channel, auto_read.status_after_turn(patterns, channel, said))
