"""A brief's parent and children, looked up by its Lemon-ID."""

import dataclasses
import sqlite3
from pathlib import Path

from ..inbox import db
from ..lineage import links
from . import lemon, render, status


def _session_name(conn: sqlite3.Connection, path: Path | None) -> str:
    """The name of the session *path* is attached to, or "" when it has none."""
    attached = (
        conn.execute("SELECT channel FROM session_briefs WHERE path = ?", (str(path),)).fetchone()
        if path
        else None
    )
    newest = db.get_by_channel(conn, attached["channel"], unread_only=False) if attached else None
    return newest.name if newest and newest.name else ""


def _child(conn: sqlite3.Connection, lemon_id: str) -> render.Child:
    current = lemon.current(conn, lemon_id)
    path = lemon.brief_of(conn, current)
    return render.Child(
        status.split(path.read_text()).status if path and path.is_file() else "",
        _session_name(conn, path) or current.split(".", 1)[0],
        current,
    )


def _with_family(conn: sqlite3.Connection, section: render.Section) -> render.Section:
    if not section.lemon_id:
        return section

    parent = links.parent_of(conn, section.lemon_id)
    return dataclasses.replace(
        section,
        parent=parent,
        parent_name=_session_name(conn, lemon.brief_of(conn, parent)) if parent else "",
        children=tuple(_child(conn, child) for child in links.children_of(conn, section.lemon_id)),
    )


def added(shown: render.View) -> render.View:
    """*shown* with each section's parent and children filled in from the database."""
    if not any(section.lemon_id for section in shown.sections):
        return shown

    with db.connect() as conn:
        sections = tuple(_with_family(conn, section) for section in shown.sections)
    return dataclasses.replace(shown, sections=sections)
