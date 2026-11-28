"""An OpenClaw lemon's inbox row when one of its turns ends."""

import re
import sqlite3
import time
from collections import abc

from .. import auto_read, rules_config
from ..inbox import db
from ..log import get_logger
from ..rules import end_of_turn, report
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


def _check_rules(
    session_key: str, channel: str, said: str, rules: rules_config.RulesConfig
) -> None:
    """Report what *said* matches; a `tell` pattern's rule goes to the lemon as its next turn,
    since its turn is already over."""
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    cwd = str(row.metadata.get("cwd") or "") if row else ""
    told = end_of_turn.check(
        channel, "openclaw", cwd, f"OpenClaw session {session_key}", said, rules, time.time()
    )
    if told:
        report.send(
            channel, channel, "\n\n".join(report.telling(each, after_turn=True) for each in told)
        )


def settle(
    session_key: str,
    said: str,
    patterns: abc.Sequence[re.Pattern[str]],
    rules: rules_config.RulesConfig,
    failed: bool,
) -> None:
    """*said* is the turn's final message, or "" when it has none or it can't be read. Runs on
    a process's main thread, where the rule check's regex time limit works."""
    channel = sessions.channel(session_key)
    with db.connect() as conn:
        _mark(conn, channel, auto_read.status_after_turn(patterns, channel, "" if failed else said))
    if said and not failed:
        _check_rules(session_key, channel, said, rules)
