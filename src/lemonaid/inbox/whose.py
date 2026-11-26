import sqlite3

from .. import brief
from . import db


def _named(channel: str, brief_id: str) -> str:
    return f"{brief_id} ({channel})" if brief_id else channel


def about(conn: sqlite3.Connection, channel: str) -> dict:
    """The session's Brief-ID and directory, and whether it is the caller's own: `yours` is None
    when the caller can't be told (`--self` would fail), and `warning` says so when it isn't."""
    try:
        caller = brief.lemon.self_channel(conn)
    except LookupError:
        caller = ""
    briefs = brief.identity.by_channel(conn)
    row = db.get_by_channel(conn, channel, unread_only=False)
    yours = (channel == caller) if caller else None
    return {
        "brief_id": briefs.get(channel, ""),
        "cwd": str((row.metadata.get("cwd") if row else "") or ""),
        "yours": yours,
        "warning": f"That session is not yours: you are {_named(caller, briefs.get(caller, ''))}."
        " To change your own, use --self."
        if yours is False
        else "",
    }


def told(channel: str, said: dict) -> list[str]:
    return [
        f"  session: {_named(channel, said['brief_id'])}",
        *([f"  directory: {said['cwd']}"] if said["cwd"] else []),
        *([f"  {said['warning']}"] if said["warning"] else []),
    ]
