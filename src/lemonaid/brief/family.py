"""A brief's parent and children, looked up by its Lemon-ID."""

import dataclasses
import functools
import os
import sqlite3
from collections import abc
from pathlib import Path

from ..inbox import db
from ..lineage import links
from . import identity, lemon, render, status


def _channels(conn: sqlite3.Connection) -> dict[str, str]:
    """Each attached brief's channel by path, read once for all of a lead's children."""
    rows = conn.execute("SELECT path, channel FROM session_briefs ORDER BY rowid DESC")
    return {row["path"]: row["channel"] for row in rows}  # the oldest attachment wins


def _session_row(
    conn: sqlite3.Connection, channels: abc.Mapping[str, str], path: Path | None
) -> db.Notification | None:
    channel = channels.get(str(path)) if path else None
    return db.get_by_channel(conn, channel, unread_only=False) if channel else None


def _session_name(
    conn: sqlite3.Connection, channels: abc.Mapping[str, str], path: Path | None
) -> str:
    row = _session_row(conn, channels, path)
    return row.name if row and row.name else ""


def _version(stat: os.stat_result) -> tuple[int, ...]:
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


@functools.lru_cache(maxsize=1024)
def _status(path: Path, version: tuple[int, ...]) -> str:
    """Keyed on the file's stat so a brief view's refresh re-reads only changed briefs.

    ctime and inode catch an edit, or a rename over the brief, that keeps its mtime and size.
    """
    return status.split(path.read_text()).status


def _child(
    conn: sqlite3.Connection, channels: abc.Mapping[str, str], lemon_id: str
) -> render.Child:
    current = lemon.current(conn, lemon_id)
    path = lemon.brief_of(conn, current)
    row = _session_row(conn, channels, path)
    return render.Child(
        _status(path, _version(path.stat())) if path and path.is_file() else "",
        (row.name if row else "") or identity.brief_description(current),
        current,
    )


def _with_family(conn: sqlite3.Connection, section: render.Section) -> render.Section:
    if not section.lemon_id:
        return section

    parent = links.parent_of(conn, section.lemon_id)
    channels = _channels(conn)
    return dataclasses.replace(
        section,
        parent=parent,
        parent_name=_session_name(conn, channels, lemon.brief_of(conn, parent)) if parent else "",
        children=tuple(
            _child(conn, channels, child_id)
            for child_id in links.live_children_of(conn, section.lemon_id)
        ),
    )


def added(shown: render.View) -> render.View:
    """*shown* with each section's parent and children filled in from the database."""
    if not any(section.lemon_id for section in shown.sections):
        return shown

    with db.connect() as conn:
        sections = tuple(_with_family(conn, section) for section in shown.sections)
    return dataclasses.replace(shown, sections=sections)
