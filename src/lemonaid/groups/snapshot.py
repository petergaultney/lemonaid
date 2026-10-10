"""A group's whole state at one moment, so an inbox edit to it can be undone.

Restoring puts back the name, place, collapse and members, with their join
times, so the group sorts and draws as it did. A group that didn't exist is
restored by deleting it. A change is undone only while its groups are as it
left them: SQLite reuses a deleted group's ID, and the CLI may have edited it.
"""

import dataclasses
import sqlite3
from collections import abc

from . import store


@dataclasses.dataclass(frozen=True)
class Snapshot:
    group_id: int
    row: tuple[str, float, int] | None  # name, position, collapsed; None when it didn't exist
    members: tuple[tuple[str, float], ...] = ()  # Lemon-ID and when it joined


class Changed(store.GroupError):
    """A group is no longer as the change left it, so the change can't be undone."""


@dataclasses.dataclass(frozen=True)
class Change:
    before: tuple[Snapshot, ...]
    after: tuple[Snapshot, ...]


def absent(group_id: int) -> Snapshot:
    """A group that doesn't exist yet: restoring it deletes the group made since."""
    return Snapshot(group_id, None)


def capture(conn: sqlite3.Connection, group_ids: abc.Iterable[int]) -> tuple[Snapshot, ...]:
    def one(group_id: int) -> Snapshot:
        row = conn.execute(
            "SELECT name, position, collapsed FROM lemon_groups WHERE group_id = ?", (group_id,)
        ).fetchone()
        return Snapshot(
            group_id,
            (row["name"], row["position"], row["collapsed"]) if row else None,
            tuple(
                (member["lemon_id"], member["added_at"])
                for member in conn.execute(
                    "SELECT lemon_id, added_at FROM lemon_group_members WHERE group_id = ?"
                    " ORDER BY lemon_id",
                    (group_id,),
                )
            ),
        )

    return tuple(one(group_id) for group_id in dict.fromkeys(group_ids))


def _members_now(conn: sqlite3.Connection, group_id: int) -> list[str]:
    return [
        row["lemon_id"]
        for row in conn.execute(
            "SELECT lemon_id FROM lemon_group_members WHERE group_id = ?", (group_id,)
        )
    ]


def restore(conn: sqlite3.Connection, change: Change) -> list[str]:
    """Put each group back as it was before *change*. Returns the lemons it moved.

    Raises GroupError, changing nothing, when a group is no longer as *change*
    left it, or its old name has been taken since.
    """
    if capture(conn, (s.group_id for s in change.after)) != change.after:
        raise Changed("The group has changed since")

    touched: list[str] = []
    try:
        for snapshot in change.before:
            touched += [*_members_now(conn, snapshot.group_id), *(m for m, _ in snapshot.members)]
            conn.execute("DELETE FROM lemon_group_members WHERE group_id = ?", (snapshot.group_id,))
            if snapshot.row is None:
                conn.execute("DELETE FROM lemon_groups WHERE group_id = ?", (snapshot.group_id,))
                continue

            conn.execute(
                "INSERT INTO lemon_groups (group_id, name, position, collapsed)"
                " VALUES (?, ?, ?, ?) ON CONFLICT (group_id) DO UPDATE SET"
                " name = excluded.name, position = excluded.position,"
                " collapsed = excluded.collapsed",
                (snapshot.group_id, *snapshot.row),
            )
            conn.executemany(
                "INSERT INTO lemon_group_members (group_id, lemon_id, added_at) VALUES (?, ?, ?)",
                [(snapshot.group_id, *member) for member in snapshot.members],
            )
    except sqlite3.IntegrityError:
        conn.rollback()
        raise store.GroupError("Another group has taken that name since") from None

    conn.commit()
    return list(dict.fromkeys(touched))
