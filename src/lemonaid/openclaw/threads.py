"""So every OpenClaw lemon finds itself (`--self`) without registering.

The record is the plugin's own state in OpenClaw's state database, not a published interface:
one that is missing or reads differently leaves a lemon to register itself as before.
"""

import json
import sqlite3
import typing as ty
from collections import abc
from pathlib import Path

from ..log import get_logger
from . import sessions

_log = get_logger("openclaw.threads")

STATE_DB = Path.home() / ".openclaw" / "state" / "openclaw.sqlite"


class Thread(ty.NamedTuple):
    id: str
    codex_home: str  # where its rollout is, for reading its context


def _thread(value: str) -> tuple[str, Thread] | None:
    record = json.loads(value)
    binding = record.get("binding") or {}
    session_id, thread = str(record.get("sessionId") or ""), str(binding.get("threadId") or "")
    if record.get("state") != "active" or not session_id or not thread:
        return None

    rollout = str(binding.get("rolloutPath") or "")
    return session_id, Thread(
        thread, rollout.split("/sessions/")[0] if "/sessions/" in rollout else ""
    )


def running(state_db: Path) -> dict[str, Thread]:
    """The Codex thread of each OpenClaw session, by OpenClaw's session id; empty, and logged,
    when the record can't be read."""
    if not state_db.exists():
        return {}

    try:
        with sqlite3.connect(f"file:{state_db}?mode=ro", uri=True, timeout=5) as state:
            values = state.execute(
                "SELECT value_json FROM plugin_state_entries"
                " WHERE plugin_id = 'codex' AND namespace = 'app-server-thread-bindings'"
            ).fetchall()
        return dict(found for (value,) in values if (found := _thread(value)))
    except (sqlite3.Error, ValueError, AttributeError) as error:
        _log.warning("can't read OpenClaw's Codex threads from %s: %s", state_db, error)
        return {}


def bind(
    conn: sqlite3.Connection,
    found: abc.Iterable[sessions.Session],
    threads: abc.Mapping[str, Thread],
) -> list[str]:
    """A thread belongs to one lemon, so binding it takes it from any other. Returns the
    channels changed."""
    bound = []
    for each in found:
        thread = threads.get(each.session_id)
        if not thread:
            continue

        channel = sessions.channel(each.key)
        conn.execute(
            "UPDATE notifications SET metadata = json_set(metadata, '$.codex_thread', '')"
            " WHERE channel LIKE ? AND channel != ? AND json_extract(metadata, '$.codex_thread') = ?",
            (sessions.PREFIX + "%", channel, thread.id),
        )
        if conn.execute(
            "UPDATE notifications SET metadata = json_set(metadata, '$.codex_thread', ?,"
            " '$.codex_home', ?, '$.session_id', ?)"
            " WHERE id = (SELECT MAX(id) FROM notifications WHERE channel = ?)"
            " AND COALESCE(json_extract(metadata, '$.codex_thread'), '') != ?",
            (thread.id, thread.codex_home, each.session_id, channel, thread.id),
        ).rowcount:
            bound.append(channel)
    conn.commit()
    return bound
