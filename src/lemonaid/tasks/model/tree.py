"""Tasks connected to a brief's lemon tree: held or specified by it or a descendant.

Membership comes from `lemon_parents`, never from task dependencies, and a task leaves the
listing once nothing in the tree holds or specifies it.
"""

import sqlite3
import typing as ty

from ...lineage import links
from . import dependencies, identities

_CONNECTIONS = (
    ("holder", "holder"),
    ("spec", "spec_brief_id"),
)


def _aliases(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["old_id"]: row["lemon_id"] for row in conn.execute("SELECT * FROM lemon_aliases")}


def _brief(value: str, column: str) -> str:
    if column != "holder":
        return value

    return value.removeprefix("brief:") if value.startswith("brief:") else ""


def rows(conn: sqlite3.Connection, brief_id: str, include_closed: bool) -> list[dict[str, ty.Any]]:
    """One row per task, with every tree brief it connects to and how."""
    root = identities.current(conn, brief_id)
    members = {root, *links.descendants(conn, root)}
    aliases = _aliases(conn)
    found = []
    for task in conn.execute(
        "SELECT * FROM tasks WHERE lifecycle != 'closed' OR ? ORDER BY created_at, task_id",
        (include_closed,),
    ):
        connections = [
            {"brief_id": current, "kind": kind}
            for kind, column in _CONNECTIONS
            if (named := _brief(task[column], column))
            and (current := aliases.get(named, named)) in members
        ]
        if connections:
            found.append(
                {
                    **dict(task),
                    "waits_for": dependencies.waits_for(conn, task["task_id"]),
                    "connections": connections,
                }
            )
    return found
