"""Named groups of lemons, keyed on Lemon-ID so membership follows the work.

A lemon can be in any number of groups, and a group can hold a lemon whose
brief isn't attached yet. Nothing here reads briefs or tmux: a group is a name,
an order, and a set of Lemon-IDs. Each member brief's `Groups:` line copies its
memberships so they travel with the file; `sync` writes it.
"""

import dataclasses
import sqlite3
import time
import unicodedata
from collections import abc

from ..log import get_logger

_log = get_logger("groups")

_SPACING = 10.0


class GroupError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class Group:
    group_id: int
    name: str
    position: float
    members: tuple[str, ...]  # Lemon-IDs, in the order they joined
    collapsed: bool = False


def checked_name(name: str) -> str:
    """*name* without surrounding space. Raises GroupError for an empty or unprintable one."""
    stripped = name.strip()
    if not stripped:
        raise GroupError("A group needs a name")

    if any(unicodedata.category(char).startswith("C") for char in stripped):
        raise GroupError(f"Group name {name!r} has a control character")

    if "," in stripped:
        raise GroupError(f"Group name {name!r} has a comma, which separates names in a brief")

    return stripped


def _members(conn: sqlite3.Connection, group_id: int) -> tuple[str, ...]:
    return tuple(
        row["lemon_id"]
        for row in conn.execute(
            "SELECT lemon_id FROM lemon_group_members WHERE group_id = ?"
            " ORDER BY added_at, lemon_id",
            (group_id,),
        )
    )


def _group(conn: sqlite3.Connection, row: sqlite3.Row) -> Group:
    return Group(
        row["group_id"],
        row["name"],
        row["position"],
        _members(conn, row["group_id"]),
        bool(row["collapsed"]),
    )


def find(conn: sqlite3.Connection, name: str) -> Group:
    """The group called *name*. Raises LookupError if there is none."""
    row = conn.execute(
        "SELECT * FROM lemon_groups WHERE name = ?", (checked_name(name),)
    ).fetchone()
    if row is None:
        raise LookupError(f"No group named {name.strip()!r}")

    return _group(conn, row)


def all_groups(conn: sqlite3.Connection) -> list[Group]:
    """Every group, in inbox order."""
    return [
        _group(conn, row)
        for row in conn.execute("SELECT * FROM lemon_groups ORDER BY position, group_id")
    ]


def groups_of(conn: sqlite3.Connection, lemon_id: str) -> list[Group]:
    """The groups *lemon_id* belongs to, in inbox order."""
    return [
        _group(conn, row)
        for row in conn.execute(
            "SELECT g.* FROM lemon_groups g JOIN lemon_group_members m USING (group_id)"
            " WHERE m.lemon_id = ? ORDER BY g.position, g.group_id",
            (lemon_id,),
        )
    ]


def _insert(conn: sqlite3.Connection, name: str) -> None:
    conn.execute(
        "INSERT INTO lemon_groups (name, position) VALUES (?, ?)",
        (
            name,
            (conn.execute("SELECT MAX(position) FROM lemon_groups").fetchone()[0] or 0) + _SPACING,
        ),
    )


def names_of(conn: sqlite3.Connection, lemon_id: str) -> tuple[str, ...]:
    return tuple(group.name for group in groups_of(conn, lemon_id))


def create(conn: sqlite3.Connection, name: str) -> Group:
    """A new, empty group below every other. Refuses a name already taken."""
    name = checked_name(name)
    try:
        _insert(conn, name)
    except sqlite3.IntegrityError:
        raise GroupError(f"A group named {name!r} already exists") from None

    conn.commit()
    return find(conn, name)


def _join(conn: sqlite3.Connection, group_id: int, lemon_id: str) -> bool:
    return bool(
        conn.execute(
            "INSERT OR IGNORE INTO lemon_group_members (group_id, lemon_id, added_at)"
            " VALUES (?, ?, ?)",
            (group_id, lemon_id, time.time()),
        ).rowcount
    )


def add(conn: sqlite3.Connection, group: Group, lemon_ids: abc.Iterable[str]) -> list[str]:
    """Put each lemon in *group*. Returns the ones that weren't members already."""
    added = [
        lemon_id for lemon_id in dict.fromkeys(lemon_ids) if _join(conn, group.group_id, lemon_id)
    ]
    conn.commit()
    return added


def remove(conn: sqlite3.Connection, group: Group, lemon_ids: abc.Iterable[str]) -> list[str]:
    """Take each lemon out of *group*. Returns the ones that were members."""
    removed = [
        lemon_id
        for lemon_id in dict.fromkeys(lemon_ids)
        if conn.execute(
            "DELETE FROM lemon_group_members WHERE group_id = ? AND lemon_id = ?",
            (group.group_id, lemon_id),
        ).rowcount
    ]
    conn.commit()
    return removed


def rename(conn: sqlite3.Connection, group: Group, name: str) -> Group:
    name = checked_name(name)
    try:
        conn.execute("UPDATE lemon_groups SET name = ? WHERE group_id = ?", (name, group.group_id))
    except sqlite3.IntegrityError:
        raise GroupError(f"A group named {name!r} already exists") from None

    conn.commit()
    return find(conn, name)


def delete(conn: sqlite3.Connection, group: Group) -> None:
    """Remove *group* and its memberships. The lemons themselves are untouched."""
    conn.execute("DELETE FROM lemon_group_members WHERE group_id = ?", (group.group_id,))
    conn.execute("DELETE FROM lemon_groups WHERE group_id = ?", (group.group_id,))
    conn.commit()


def replace_memberships(conn: sqlite3.Connection, lemon_id: str, names: abc.Iterable[str]) -> None:
    """Make *lemon_id* a member of exactly the groups *names*, creating any that don't exist.

    Doesn't commit, so a caller holding a transaction keeps it. A name that
    isn't a valid group name is logged and skipped.
    """
    conn.execute("DELETE FROM lemon_group_members WHERE lemon_id = ?", (lemon_id,))
    for raw in names:
        try:
            name = checked_name(raw)
        except GroupError as error:
            _log.warning("Not joining %s to a group: %s", lemon_id, error)
            continue

        if conn.execute("SELECT 1 FROM lemon_groups WHERE name = ?", (name,)).fetchone() is None:
            _insert(conn, name)
        group_id = conn.execute(
            "SELECT group_id FROM lemon_groups WHERE name = ?", (name,)
        ).fetchone()["group_id"]
        _join(conn, group_id, lemon_id)
