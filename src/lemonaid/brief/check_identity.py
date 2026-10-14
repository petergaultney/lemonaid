"""Checks against the identity and group records attached to a brief."""

import sqlite3
from pathlib import Path

from .. import groups
from . import identity


def recorded(conn: sqlite3.Connection, path: Path, text: str) -> list[str]:
    """Whether the brief's ID is the one the database records for *path*."""
    try:
        in_file = identity.read(text)
    except ValueError:
        return []  # structure() reports it

    row = conn.execute(
        "SELECT lemon_id FROM lemon_identities WHERE path = ?", (str(path.resolve()),)
    ).fetchone()
    if row and row["lemon_id"] != in_file:
        return [f"Brief-ID is {in_file or 'missing'}, but this brief is {row['lemon_id']}"]

    if row or not in_file:
        return []

    alias = conn.execute(
        "SELECT lemon_id FROM lemon_aliases WHERE old_id = ?", (in_file,)
    ).fetchone()
    if alias:
        return [f"Brief-ID {in_file} is an old ID of {alias['lemon_id']}"]

    holder = conn.execute(
        "SELECT path FROM lemon_identities WHERE lemon_id = ?", (in_file,)
    ).fetchone()
    return [f"Brief-ID {in_file} belongs to {holder['path']}"] if holder else []


def groups_line(conn: sqlite3.Connection, text: str) -> list[str]:
    """A `Groups:` line that disagrees with the groups the database records for the brief."""
    try:
        lemon_id = identity.read(text)
    except ValueError:
        return []  # structure() reports it

    known = conn.execute(
        "SELECT 1 FROM lemon_identities WHERE lemon_id = ?", (lemon_id,)
    ).fetchone()
    if not known:
        return []  # registering the brief reads its line in

    expected = groups.store.names_of(conn, lemon_id)
    written = groups.line.read(text) or ()
    if set(written) == set(expected):
        return []

    if not expected:
        return ["The `Groups:` line names groups this brief isn't in; remove it"]

    return [f"The `Groups:` line should read `{groups.line.render(expected)}`"]
