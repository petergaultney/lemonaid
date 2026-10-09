"""How one machine's inbox lays groups out: their order, and which are collapsed.

Neither travels with a brief: they're how one person reads their inbox.
"""

import sqlite3

from . import store


def set_collapsed(conn: sqlite3.Connection, group: store.Group, collapsed: bool) -> None:
    conn.execute(
        "UPDATE lemon_groups SET collapsed = ? WHERE group_id = ?", (int(collapsed), group.group_id)
    )
    conn.commit()


def swap(conn: sqlite3.Connection, group: store.Group, other: store.Group) -> None:
    """Exchange two groups' places in the order."""
    conn.executemany(
        "UPDATE lemon_groups SET position = ? WHERE group_id = ?",
        [(other.position, group.group_id), (group.position, other.group_id)],
    )
    conn.commit()
