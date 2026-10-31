"""Brief IDs in task records keep the ID they were written with; reads resolve them.

A reroll aliases the old Lemon-ID to the new one, so a task held by the old ID is still
held by the same brief.
"""

import sqlite3

from ...brief import lemon


def current(conn: sqlite3.Connection, brief_id: str) -> str:
    return lemon.current(conn, brief_id) if brief_id else ""


def names(conn: sqlite3.Connection, brief_id: str) -> list[str]:
    """Every ID that means *brief_id*'s brief: its current one first, then old ones."""
    now = current(conn, brief_id)
    return [
        now,
        *(
            row["old_id"]
            for row in conn.execute(
                "SELECT old_id FROM lemon_aliases WHERE lemon_id = ? ORDER BY old_id", (now,)
            )
        ),
    ]


def placeholders(values: list[str]) -> str:
    return ", ".join("?" for _ in values)
