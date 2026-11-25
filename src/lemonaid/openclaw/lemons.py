"""OpenClaw sessions as lemons: an inbox row per session key, found again from inside it.

Nothing in a shell command's environment names its OpenClaw session, only the Codex thread
running it. So a session registers itself, giving the key its `session_status` tool reports,
and the row remembers the thread; a later command from the same thread finds the row by it.
OpenClaw starts a new thread after a reset or compaction, after which the session registers
again.
"""

import os
import sqlite3
import typing as ty
from pathlib import Path

from ..inbox import db
from . import sessions


class NotRegistered(LookupError):
    pass


def _register_hint() -> str:
    return (
        "this OpenClaw session is not registered with lemonaid; get your session key from"
        " the session_status tool and run `lemonaid openclaw register --session-key <key>`"
    )


def register(
    conn: sqlite3.Connection,
    found: sessions.Session,
    thread: str,
    codex_home: Path | None,
    cwd: str,
    front_end: str,
    name: str = "",
    extra: dict[str, ty.Any] | None = None,
) -> db.Notification:
    """Record *found* as a lemon shown through *front_end*, bound to the Codex *thread*
    now running it, which no other OpenClaw lemon then holds; *name* defaults to its agent's
    id."""
    channel = sessions.channel(found.key)
    if thread:
        conn.execute(
            "UPDATE notifications SET metadata = json_set(metadata, '$.codex_thread', '')"
            " WHERE channel LIKE ? AND channel != ? AND json_extract(metadata, '$.codex_thread') = ?",
            (sessions.PREFIX + "%", channel, thread),
        )
    row = db.register_working(
        conn,
        channel,
        f"OpenClaw session {found.key}",
        name=name or found.agent_id or None,
        metadata={
            "session_key": found.key,
            "session_id": found.session_id,
            "agent_id": found.agent_id,
            "codex_thread": thread,
            "codex_home": str(codex_home or ""),
            "cwd": cwd,
            **(extra or {}),
        },
        switch_source=front_end,
    )
    if found.context_tokens:
        db.record_context(conn, channel, found.total_tokens, found.context_tokens)
    return row


def by_thread(conn: sqlite3.Connection, thread: str) -> str:
    """The channel of the OpenClaw lemon bound to Codex *thread*, or ""."""
    row = conn.execute(
        "SELECT channel FROM notifications WHERE channel LIKE ?"
        " AND json_extract(metadata, '$.codex_thread') = ? ORDER BY id DESC LIMIT 1",
        (sessions.PREFIX + "%", thread),
    ).fetchone()
    return row[0] if row else ""


def self_channel(conn: sqlite3.Connection) -> str:
    """The caller's channel, when OpenClaw runs it. Raises `NotRegistered`."""
    thread = os.environ.get("CODEX_THREAD_ID", "")
    found = by_thread(conn, thread) if thread else ""
    if not found:
        raise NotRegistered(_register_hint())

    return found
