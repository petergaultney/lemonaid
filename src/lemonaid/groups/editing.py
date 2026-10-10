"""Group changes made from the inbox, each with what it takes to undo it.

Every change rewrites the `Groups:` line of each brief it touches, as the CLI
does, and reports the briefs it couldn't write.
"""

import dataclasses
import re
import sqlite3
import unicodedata

from .. import lineage
from . import snapshot, store, sync


def _changed(conn: sqlite3.Connection, before: tuple[snapshot.Snapshot, ...]) -> snapshot.Change:
    """*before*, and its groups as they are now."""
    return snapshot.Change(before, snapshot.capture(conn, (s.group_id for s in before)))


@dataclasses.dataclass(frozen=True)
class Edit:
    description: str  # what the inbox's toast says was done
    change: snapshot.Change
    unwritten: list[str]
    group: store.Group | None = None  # the group as it is now, None once deleted


def valid_name(wanted: str) -> str:
    """*wanted* as a group name: commas and control characters made spaces, runs of space one."""
    return (
        re.sub(
            r"\s+",
            " ",
            "".join(
                " " if char == "," or unicodedata.category(char).startswith("C") else char
                for char in wanted
            ),
        ).strip()
        or "Group"
    )


def group_tree(conn: sqlite3.Connection, lemon_id: str, name: str, lemon_name: str) -> Edit:
    """Put *lemon_id*, its children, their children... in the group *name*, made if need be.

    Raises GroupError for an invalid name, or when they're all members already.
    """
    try:
        group = store.find(conn, name)
        before = snapshot.capture(conn, [group.group_id])
        made = bool(not group.members)
    except LookupError:
        group = store.create(conn, name)
        before = (snapshot.absent(group.group_id),)
        made = True
    added = store.add(conn, group, [lemon_id, *lineage.links.descendants(conn, lemon_id)])
    if not added:
        raise store.GroupError(f'{lemon_name} and its children are already in "{group.name}"')

    if lemon_id not in added:
        who = f"{len(added)} of {lemon_name}'s children"
    else:
        who = lemon_name + (f" and {len(added) - 1} more" if len(added) > 1 else "")
    return Edit(
        f'Made group "{group.name}" of {who}' if made else f'Added {who} to "{group.name}"',
        _changed(conn, before),
        sync.write_lines(conn, added),
        store.find(conn, group.name),
    )


def add(conn: sqlite3.Connection, name: str, lemon_id: str, lemon_name: str) -> Edit:
    """Put *lemon_id* in the group *name*, making the group if there isn't one.

    Raises GroupError when it's a member already.
    """
    try:
        group = store.find(conn, name)
        before = snapshot.capture(conn, [group.group_id])
        made = ""
    except LookupError:
        group = store.create(conn, name)
        before = (snapshot.absent(group.group_id),)
        made = " (new)"

    if not store.add(conn, group, [lemon_id]):
        raise store.GroupError(f'{lemon_name} is already in "{group.name}"')

    return Edit(
        f'Added {lemon_name} to "{group.name}"{made}',
        _changed(conn, before),
        sync.write_lines(conn, [lemon_id]),
        store.find(conn, group.name),
    )


def remove(conn: sqlite3.Connection, group: store.Group, lemon_id: str, lemon_name: str) -> Edit:
    before = snapshot.capture(conn, [group.group_id])
    store.remove(conn, group, [lemon_id])
    return Edit(
        f'Took {lemon_name} out of "{group.name}"',
        _changed(conn, before),
        sync.write_lines(conn, [lemon_id]),
        store.find(conn, group.name),
    )


def rename(conn: sqlite3.Connection, group: store.Group, name: str) -> Edit:
    """Raises GroupError for a name that's invalid or taken."""
    before = snapshot.capture(conn, [group.group_id])
    renamed = store.rename(conn, group, name)
    return Edit(
        f'Renamed group "{group.name}" to "{renamed.name}"',
        _changed(conn, before),
        sync.write_lines(conn, renamed.members),
        renamed,
    )


def delete(conn: sqlite3.Connection, group: store.Group) -> Edit:
    before = snapshot.capture(conn, [group.group_id])
    store.delete(conn, group)
    return Edit(
        f'Deleted group "{group.name}"',
        _changed(conn, before),
        sync.write_lines(conn, group.members),
    )


def undo(conn: sqlite3.Connection, change: snapshot.Change) -> list[str]:
    """Put the groups back as they were before *change*. Returns the briefs it couldn't write.

    Raises GroupError when they've changed since, or a group's old name has been taken.
    """
    return sync.write_lines(conn, snapshot.restore(conn, change))
