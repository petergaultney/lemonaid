"""Parent precedence within one group's visible rows."""

import sqlite3
from collections import abc

from . import db


def channels(conn: sqlite3.Connection) -> dict[str, str]:
    """Resolve the same stable parent links used by `brief children` to attached channels."""
    return {
        row["child"]: row["parent"]
        for row in conn.execute(
            "SELECT c.channel AS child, p.channel AS parent FROM lemon_parents l"
            " JOIN lemon_identities ci ON ci.lemon_id = l.lemon_id"
            " JOIN session_briefs c ON c.path = ci.path"
            " JOIN lemon_identities pi ON pi.lemon_id = l.parent_id"
            " JOIN session_briefs p ON p.path = pi.path"
        )
    }


def ordered(
    rows: abc.Sequence[db.Notification], parents: abc.Mapping[str, str]
) -> list[db.Notification]:
    """Promote visible ancestors before their first child, keeping siblings in input order."""
    by_channel = {n.channel: n for n in rows}
    dependencies: dict[str, list[str]] = {}
    previous: dict[str, str] = {}
    for row in rows:
        parent = parents.get(row.channel, "")
        if parent in by_channel and parent != row.channel:
            dependencies[row.channel] = [parent]
            if parent in previous:
                dependencies[row.channel].append(previous[parent])
            previous[parent] = row.channel

    result = []
    visited: set[str] = set()
    for row in rows:
        stack = [(row.channel, False)]
        while stack:
            channel, emit = stack.pop()
            if emit:
                result.append(by_channel[channel])
            elif channel not in visited:
                visited.add(channel)  # Cycles terminate without drawing a row twice.
                stack.append((channel, True))
                stack.extend((p, False) for p in reversed(dependencies.get(channel, ())))
    return result
