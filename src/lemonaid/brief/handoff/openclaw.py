"""Start a handoff's receiver as a new OpenClaw session, the way `lemon start` does in one.

There is no pane to replace, so once the outgoing lemon is ready the receiver starts as a
root session of the outgoing lemon's agent when that is an OpenClaw lemon, else of the
gateway's default agent. The outgoing session is left as it is; the transfer archives its
lemon.
"""

import sqlite3
from collections import abc
from pathlib import Path

from ...front_end import chat
from ...inbox import db
from ...launch import handoff, openclaw_session
from ...openclaw import lemons, sessions, sync


def _agent(conn: sqlite3.Connection, source: str) -> sync.Agent:
    try:
        agents = sync.agents(sessions.cli())
    except sessions.Unavailable as error:
        raise OSError(str(error)) from error

    row = db.get_by_channel(conn, source, unread_only=False)
    own = str(row.metadata.get("agent_id") or "") if row else ""
    found = agents.get(own) or next((each for each in agents.values() if each.default), None)
    if found is None:
        raise ValueError("OpenClaw has no default agent to start the new lemon in")

    return found


def start(conn: sqlite3.Connection, row: sqlite3.Row, launched: abc.Callable[[str], None]) -> None:
    """Raises ValueError or OSError."""
    found = openclaw_session.new_session(
        conn,
        _agent(conn, row["source"]),
        handoff.session_title(handoff.Handoff(brief=Path(row["path"]))),
    )
    launched(sessions.channel(found.key))
    prompt = (
        f"Read {row['path']}, especially ## Handoff. Rearm ## Waiters, then run "
        f"lemonaid brief handoff accept {row['token']}. "
        "Your brief will attach only after that acknowledgement."
    )
    if error := chat.send(found.key, openclaw_session.first_message(found.key, prompt)):
        raise OSError(error)


def own_channel(conn: sqlite3.Connection) -> str:
    try:
        return lemons.self_channel(conn)
    except lemons.NotRegistered:
        return ""


def request_note(channel: str, brief: Path) -> str:
    """A session gets a new Codex thread after a reset, which its `--self` commands can't
    find until it registers again."""
    return (
        f"{openclaw_session.register_line(sessions.session_key(channel))} Your brief is {brief}. "
    )
