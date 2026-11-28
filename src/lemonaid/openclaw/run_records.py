"""An OpenClaw lemon's turns as its plugin reports them, by run, in its inbox row.

The row's `turn_at` says the turn is running as of then, and its metadata says when the latest
turn started and the last one ended (`turn_started_at`, `turn_ended_at`), as the gateway's events
record them (`turns`). `turn_run` names the run that started the latest turn, so the same run
reported again keeps its start, and `turn_ended_run` the run that ended last, so a report from a
run already over doesn't reopen it.
"""

import sqlite3

from . import sessions


def running(conn: sqlite3.Connection, session_key: str, run: str, at: float) -> int:
    """Taken unless the row holds a later report: a turn running as of *at* or after, or one
    that ended then or after; or *run* has ended. A report without a run belongs to the turn
    already running, if one is."""
    cursor = conn.execute(
        """
        UPDATE notifications SET metadata = json_set(
            coalesce(metadata, '{}'),
            '$.turn_run', CASE WHEN :run = '' AND turn_at IS NOT NULL
                THEN coalesce(json_extract(metadata, '$.turn_run'), '') ELSE :run END,
            '$.turn_started_at', CASE
                WHEN turn_at IS NOT NULL
                 AND (:run = '' OR json_extract(metadata, '$.turn_run') IN (:run, ''))
                THEN json_extract(metadata, '$.turn_started_at') ELSE :at END,
            '$.turn_ended_at', coalesce(json_extract(metadata, '$.turn_ended_at'), 0)),
            turn_at = :at
        WHERE channel = :channel
          AND :at > coalesce(json_extract(metadata, '$.turn_ended_at'), 0)
          AND (turn_at IS NULL OR :at >= turn_at)
          AND (:run = '' OR coalesce(json_extract(metadata, '$.turn_ended_run'), '') != :run)
        """,
        {"at": at, "run": run, "channel": sessions.channel(session_key)},
    )
    conn.commit()
    return cursor.rowcount


def sent(conn: sqlite3.Connection, session_key: str, at: float) -> int:
    """Record a turn as running from *at*, when the gateway accepted it, unless one already is
    or a turn has ended since: the turn sent may have run and ended before this is recorded."""
    cursor = conn.execute(
        """
        UPDATE notifications SET turn_at = :at, metadata = json_set(
            coalesce(metadata, '{}'), '$.turn_run', '', '$.turn_started_at', :at,
            '$.turn_ended_at', coalesce(json_extract(metadata, '$.turn_ended_at'), 0))
        WHERE channel = :channel AND turn_at IS NULL
          AND coalesce(json_extract(metadata, '$.turn_ended_at'), 0) < :at
        """,
        {"at": at, "channel": sessions.channel(session_key)},
    )
    conn.commit()
    return cursor.rowcount


def ended(conn: sqlite3.Connection, session_key: str, run: str, at: float) -> int:
    """Taken, returning 1, unless it reports an older turn than the row holds: one that ended
    before the running turn started, or a run other than the one running."""
    cursor = conn.execute(
        """
        UPDATE notifications SET turn_at = NULL, metadata = json_set(
            coalesce(metadata, '{}'), '$.turn_ended_at', :at, '$.turn_ended_run', :run,
            '$.turn_started_at', coalesce(json_extract(metadata, '$.turn_started_at'), :at))
        WHERE channel = :channel
          AND :at >= coalesce(json_extract(metadata, '$.turn_started_at'), 0)
          AND :at >= coalesce(json_extract(metadata, '$.turn_ended_at'), 0)
          AND (turn_at IS NULL OR :run = ''
               OR coalesce(json_extract(metadata, '$.turn_run'), '') IN (:run, ''))
        """,
        {"at": at, "run": run, "channel": sessions.channel(session_key)},
    )
    conn.commit()
    return cursor.rowcount


def all_ended(conn: sqlite3.Connection, at: float) -> int:
    """End every OpenClaw lemon's turn: a gateway that has just started runs none."""
    cursor = conn.execute(
        "UPDATE notifications SET turn_at = NULL,"
        " metadata = json_set(coalesce(metadata, '{}'), '$.turn_ended_at', ?)"
        " WHERE channel LIKE ? AND turn_at IS NOT NULL",
        (at, sessions.PREFIX + "%"),
    )
    conn.commit()
    return cursor.rowcount
