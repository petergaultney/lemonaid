"""A brief's `created:` header line, written once when it is created."""

import datetime
import sqlite3

from ..log import get_logger
from . import identity, lemon

_log = get_logger("brief.created")


def by(conn: sqlite3.Connection) -> str:
    """The WordyBin of the lemon running this command, or "" when its brief has no name."""
    try:
        return identity.brief_name(lemon.own_id(conn))
    except (LookupError, ValueError) as cause:
        _log.info("No created.by: %s", cause)
        return ""


def line(at: datetime.datetime, created_by: str) -> str:
    """`created: { at: ..., by: ... }` for *at* (timezone-aware, to the second); no `by` for ""."""
    stamp = f"at: {at.replace(microsecond=0).isoformat()}"
    return f"created: {{ {stamp}, by: {created_by} }}" if created_by else f"created: {{ {stamp} }}"


def now(created_by: str) -> str:
    return line(datetime.datetime.now().astimezone(), created_by)
