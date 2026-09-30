"""A brief's parent and children, looked up by its Lemon-ID."""

import dataclasses
import sqlite3
from pathlib import Path

from ..inbox import db
from ..lineage import links
from . import identity, render, status


def _child(conn: sqlite3.Connection, lemon_id: str) -> tuple[str, str]:
    """The child's brief status, and its session's name or else its Lemon-ID's slug."""
    row = conn.execute(
        "SELECT path FROM lemon_identities WHERE lemon_id = ?", (lemon_id,)
    ).fetchone()
    path = Path(row["path"]) if row else None
    state = status.split(path.read_text()).status if path and path.is_file() else ""
    attached = (
        conn.execute("SELECT channel FROM session_briefs WHERE path = ?", (str(path),)).fetchone()
        if path
        else None
    )
    newest = db.get_by_channel(conn, attached["channel"], unread_only=False) if attached else None
    return state, (newest.name if newest and newest.name else lemon_id.split(".", 1)[0])


def of(conn: sqlite3.Connection, brief: Path) -> tuple[str, tuple[tuple[str, str], ...]]:
    """*brief*'s parent's Lemon-ID and its children, or nothing when it has no Lemon-ID."""
    try:
        lemon_id = identity.read(brief.read_text())
    except (OSError, ValueError):
        return "", ()

    if not lemon_id:
        return "", ()

    return links.parent_of(conn, lemon_id), tuple(
        _child(conn, child) for child in links.children_of(conn, lemon_id)
    )


def _with_family(conn: sqlite3.Connection, section: render.Section) -> render.Section:
    if not section.path:
        return section

    parent, children = of(conn, section.path)
    return dataclasses.replace(section, parent=parent, children=children)


def added(shown: render.View) -> render.View:
    """*shown* with each section's parent and children filled in from the database."""
    if not any(section.path for section in shown.sections):
        return shown

    with db.connect() as conn:
        sections = tuple(_with_family(conn, section) for section in shown.sections)
    return dataclasses.replace(shown, sections=sections)
