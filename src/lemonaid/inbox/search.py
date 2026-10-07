"""Search the inbox and optionally its session history."""

import sqlite3
from dataclasses import dataclass
from typing import Literal

from . import db


@dataclass(frozen=True)
class Result:
    notification: db.Notification
    source: Literal["inbox", "archive"]


def find(
    conn: sqlite3.Connection,
    query: str,
    *,
    include_history: bool = False,
    switch_source: str | None = None,
) -> list[Result]:
    """Return matching sessions newest first, once per channel."""
    where = ""
    args: list[str] = []
    if query:
        where = """
            AND (
                n.name LIKE ? ESCAPE '!' OR n.message LIKE ? ESCAPE '!'
                OR n.channel LIKE ? ESCAPE '!'
                OR json_extract(n.metadata, '$.cwd') LIKE ? ESCAPE '!'
                OR json_extract(n.metadata, '$.git_branch') LIKE ? ESCAPE '!'
                OR EXISTS (
                    SELECT 1 FROM session_briefs b
                    JOIN lemon_identities i ON i.path = b.path
                    WHERE b.channel = n.channel AND i.lemon_id LIKE ? ESCAPE '!'
                )
            )
        """
        args = [db.substring_pattern(query)] * 6

    if switch_source:
        where += " AND n.switch_source = ?"
        args.append(switch_source)

    rows = conn.execute(
        f"""
        SELECT n.* FROM notifications n
        INNER JOIN (
            SELECT channel, MAX(id) AS max_id FROM notifications
            WHERE status NOT IN ('archived', 'snoozed')
            GROUP BY channel
        ) latest ON n.id = latest.max_id
        WHERE n.status NOT IN ('archived', 'snoozed') {where}
        ORDER BY n.created_at DESC
        """,
        args,
    ).fetchall()
    active = [Result(db.Notification.from_row(row), "inbox") for row in rows]
    if not include_history:
        return active

    # A channel can be live even when its current row does not match the query
    # or belongs to a different switch source.
    channels = {row.channel for row in db.get_active(conn)}
    history = [
        Result(row, "archive")
        for row in db.get_history(conn, search=query)
        if row.channel not in channels
    ]
    return sorted(
        [*active, *history], key=lambda result: result.notification.created_at, reverse=True
    )
