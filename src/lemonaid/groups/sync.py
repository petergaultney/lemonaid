"""Keep each member brief's `Groups:` line in step with the database.

The database is what the inbox reads; the line is the copy that moves with the
brief to another machine. A brief whose Brief-ID a database has never seen has
its line read in by `brief.identity.ensure`; after that the database wins.
"""

import sqlite3
from collections import abc

from .. import brief
from ..log import get_logger
from . import line, store

_log = get_logger("groups")


def write_lines(conn: sqlite3.Connection, lemon_ids: abc.Iterable[str]) -> list[str]:
    """Rewrite each lemon's `Groups:` line from the database. Returns the briefs it couldn't write.

    A lemon with no brief file is skipped: it has nowhere to carry the line.
    `brief check` reports a line that a failed write left behind.
    """
    failed: list[str] = []
    for lemon_id in dict.fromkeys(lemon_ids):
        path = brief.lemon.brief_of(conn, lemon_id)
        if path is None or not path.is_file():
            continue

        names = store.names_of(conn, lemon_id)
        try:
            brief.store.edit(path, lambda text, names=names: line.written(text, names))
        except (OSError, brief.store.ChangedUnderneath) as error:
            _log.warning("Couldn't write the Groups: line in %s: %s", path, error)
            failed.append(str(path))

    return failed


def read_line(conn: sqlite3.Connection, lemon_id: str) -> tuple[str, ...] | None:
    """Replace *lemon_id*'s memberships with its brief's `Groups:` line, and return them.

    A brief with no line, or no brief here, says nothing about its groups, so
    they're left alone and this returns None. An empty line clears them.
    """
    path = brief.lemon.brief_of(conn, lemon_id)
    names = line.read(path.read_text()) if path and path.is_file() else None
    if names is None:
        return None

    store.replace_memberships(conn, lemon_id, names)
    conn.commit()
    return store.names_of(conn, lemon_id)


def join_parents(conn: sqlite3.Connection, child: str, parent: str) -> tuple[str, ...]:
    """Put *child* in each of *parent*'s groups and write its line. Returns their names."""
    names = store.names_of(conn, parent)
    for name in names:
        store.add(conn, store.find(conn, name), [child])
    if names:
        write_lines(conn, [child])
    return names
