"""Which lemon started which, recorded by stable Lemon-ID.

A lemon has at most one parent. Links name Lemon-IDs, never a channel, tmux
window, or brief filename, so they survive resumes, renamed briefs, and tmux
going away.
"""

import sqlite3
import time
from pathlib import Path

from .. import brief


class LinkError(ValueError):
    pass


def parent_of(conn: sqlite3.Connection, lemon_id: str) -> str:
    row = conn.execute(
        "SELECT parent_id FROM lemon_parents WHERE lemon_id = ?", (lemon_id,)
    ).fetchone()
    return row["parent_id"] if row else ""


def children_of(conn: sqlite3.Connection, lemon_id: str) -> list[str]:
    return [
        row["lemon_id"]
        for row in conn.execute(
            "SELECT lemon_id FROM lemon_parents WHERE parent_id = ? ORDER BY linked_at, lemon_id",
            (lemon_id,),
        )
    ]


# A child is gone once the newest inbox row of its brief's session is archived, or once its
# brief, attached to no session, is in the attic. Its link stays, so lineage and
# `brief children --all` still show it, but automatic child tracking stops.
_LIVE_CHILDREN = """
WITH attached AS (SELECT path, channel, MIN(rowid) FROM session_briefs GROUP BY path)
SELECT p.lemon_id FROM lemon_parents p
LEFT JOIN lemon_aliases a ON a.old_id = p.lemon_id
LEFT JOIN lemon_identities i ON i.lemon_id = COALESCE(a.lemon_id, p.lemon_id)
LEFT JOIN attached b ON b.path = i.path
WHERE p.parent_id = :parent
  AND COALESCE(
    (
      SELECT n.status FROM notifications n WHERE n.channel = b.channel
      ORDER BY n.created_at DESC LIMIT 1
    ),
    ''
  ) != 'archived'
  AND NOT (b.channel IS NULL AND substr(COALESCE(i.path, ''), 1, length(:attic)) = :attic)
ORDER BY p.linked_at, p.lemon_id
"""


def live_children_of(conn: sqlite3.Connection, lemon_id: str, attic: Path) -> list[str]:
    return [
        row["lemon_id"]
        for row in conn.execute(_LIVE_CHILDREN, {"parent": lemon_id, "attic": f"{attic}/"})
    ]


def ancestors(conn: sqlite3.Connection, lemon_id: str) -> list[str]:
    """*lemon_id*'s parent, its parent, and so on."""
    found: list[str] = []
    current = lemon_id
    while (parent := parent_of(conn, current)) and parent not in found and parent != lemon_id:
        found.append(parent)
        current = parent

    return found


def check(conn: sqlite3.Connection, lemon_id: str, parent_id: str) -> None:
    """Raise LinkError unless *parent_id* could be *lemon_id*'s parent."""
    for name in (lemon_id, parent_id):
        if not brief.identity.valid(name):
            raise LinkError(f"Invalid Lemon-ID: {name!r}")

    if parent_id == lemon_id:
        raise LinkError(f"{lemon_id} cannot be its own parent")

    if lemon_id in ancestors(conn, parent_id):
        raise LinkError(f"{parent_id} descends from {lemon_id}; linking would make a cycle")


def set_parent(conn: sqlite3.Connection, lemon_id: str, parent_id: str) -> None:
    """Replace *lemon_id*'s parent. Refuses itself, or a descendant, as the parent."""
    check(conn, lemon_id, parent_id)
    conn.execute(
        "INSERT OR REPLACE INTO lemon_parents (lemon_id, parent_id, linked_at) VALUES (?, ?, ?)",
        (lemon_id, parent_id, time.time()),
    )
    conn.commit()


def clear_parent(conn: sqlite3.Connection, lemon_id: str) -> bool:
    cursor = conn.execute("DELETE FROM lemon_parents WHERE lemon_id = ?", (lemon_id,))
    conn.commit()
    return cursor.rowcount > 0


def descendants(conn: sqlite3.Connection, lemon_id: str) -> list[str]:
    """*lemon_id*'s children, their children, and so on, each once, parents first."""
    found: list[str] = []
    frontier = [lemon_id]
    while frontier:
        fresh = [
            child
            for parent in frontier
            for child in children_of(conn, parent)
            if child != lemon_id and child not in found
        ]
        found.extend(dict.fromkeys(fresh))
        frontier = list(dict.fromkeys(fresh))

    return found
