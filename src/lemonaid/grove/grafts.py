"""Lemons the grove draws on another lemon's tree, wherever they run.

Each graft names its lemon and its host by Lemon-ID, or by channel for a lemon without a brief,
so it holds across restarts, resumes and tree renames. Nothing here reads briefs or terminals:
`source.grafting` decides where a graft puts a lemon today.
"""

import sqlite3
import time
from collections import abc


class GraftError(ValueError):
    pass


def recorded(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        row["lemon"]: row["onto"] for row in conn.execute("SELECT lemon, onto FROM tree_grafts")
    }


def listed(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every graft, oldest first, with `lemon`, `onto` and `grafted_at`."""
    return conn.execute("SELECT * FROM tree_grafts ORDER BY grafted_at, lemon").fetchall()


def graft(conn: sqlite3.Connection, lemon: str, onto: str) -> None:
    """Put *lemon* on *onto*'s tree, in place of any graft it had. Raises GraftError for a lemon
    grafted onto itself, or onto a lemon its own tree holds by a graft."""
    if lemon == onto:
        raise GraftError(f"{lemon} can't be grafted onto its own tree")

    hosts, at, seen = recorded(conn), onto, set()
    while at in hosts and at not in seen:
        seen.add(at)
        at = hosts[at]
        if at == lemon:
            raise GraftError(f"{onto} is grafted onto {lemon}'s tree; ungraft it first")
    conn.execute(
        "INSERT INTO tree_grafts (lemon, onto, grafted_at) VALUES (?, ?, ?)"
        " ON CONFLICT(lemon) DO UPDATE SET onto = excluded.onto, grafted_at = excluded.grafted_at",
        (lemon, onto, time.time()),
    )
    conn.commit()


def ungraft(conn: sqlite3.Connection, names: abc.Iterable[str]) -> int:
    """Put back on its own tree the lemon each of *names* (Lemon-IDs and channels) grafted;
    how many grafts that removed."""
    removed = sum(
        conn.execute("DELETE FROM tree_grafts WHERE lemon = ?", (name,)).rowcount
        for name in set(names)
    )
    conn.commit()
    return removed
