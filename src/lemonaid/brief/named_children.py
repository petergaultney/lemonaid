"""Lemons whose brief names a parent other than their parent link: an author's reviewers.

An author starts each reviewer with `lemon start --parent parent`, so the link names the
author's own parent, while the reviewer's brief names the author as `parent:`.
"""

import sqlite3

from ..log import get_logger
from . import attached, identity, lemon, parent

_log = get_logger("brief.named_children")


def of(conn: sqlite3.Connection, parent_id: str) -> dict[str, attached.Attachment]:
    """Each attached lemon whose brief names *parent_id* as `parent:`, by Lemon-ID."""
    found: dict[str, attached.Attachment] = {}
    for entry in {entry.path: entry for entry in attached.everything(conn)}.values():
        if not entry.path.is_file():
            continue  # a stale attachment to a brief that moved or was deleted

        try:
            named = parent.named(entry.path.read_text())
            if named and lemon.current(conn, named) == parent_id:
                found[identity.from_path(entry.path)] = entry
        except (OSError, ValueError) as error:
            _log.warning("Cannot read brief %s: %s", entry.path, error)
    return found
