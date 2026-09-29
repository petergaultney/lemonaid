"""A brief's parent and children, as one line under its card."""

import dataclasses
import sqlite3
from pathlib import Path

from ..inbox import db
from ..lineage import links
from . import identity, render, status


def _status(conn: sqlite3.Connection, lemon_id: str) -> str:
    row = conn.execute(
        "SELECT path FROM lemon_identities WHERE lemon_id = ?", (lemon_id,)
    ).fetchone()
    path = Path(row["path"]) if row else None
    return status.split(path.read_text()).status if path and path.is_file() else ""


def line(conn: sqlite3.Connection, brief: Path) -> str:
    """Markdown naming *brief*'s parent and children, or "" when it has neither."""
    try:
        lemon_id = identity.read(brief.read_text())
    except (OSError, ValueError):
        return ""

    if not lemon_id:
        return ""

    parent = links.parent_of(conn, lemon_id)
    children = [
        f"`{child}` {state}".rstrip()
        for child in links.children_of(conn, lemon_id)
        for state in [_status(conn, child)]
    ]
    return " · ".join(
        part
        for part in (
            f"**Parent:** `{parent}`" if parent else "",
            f"**Children:** {', '.join(children)}" if children else "",
        )
        if part
    )


def added(shown: render.View) -> render.View:
    """*shown* with each section's family line filled in from the database."""
    if not any(section.path for section in shown.sections):
        return shown

    with db.connect() as conn:
        sections = tuple(
            dataclasses.replace(section, family=line(conn, section.path))
            if section.path
            else section
            for section in shown.sections
        )
    return dataclasses.replace(shown, sections=sections)
