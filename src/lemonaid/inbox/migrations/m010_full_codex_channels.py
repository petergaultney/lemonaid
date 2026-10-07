"""Name Codex channels by the whole thread id instead of its first 8 characters.

Codex thread ids are UUIDv7, so threads started within about a minute share
their first 8 characters, and shared one channel. Each row's metadata gives
the full id the notify hook would now use: the rollout file's UUID first, then
the recorded thread id. A row with no full id keeps its old channel.

A subagent or approval reviewer started beside its parent shared the parent's
channel, and its notifications overwrote the parent's row. Its rollout's
`session_meta` names the root thread, so when the root shares the channel's
prefix, the row moves to the root's channel, taking the parent's brief, pin,
and emoji with it. A spawned thread on a channel of its own stays there.

Tables keyed by channel follow the newest notification on the old channel, the
thread the inbox was showing, and stay put when that row has no full id. When
the full channel already has a pin, emoji, or brief, it keeps its own.

A full channel can end up with several rows, from a database that already had
both forms or from rows added without upsert. The newest keeps its status, and
the rest are archived, as upserting them in order would have left one row.
"""

import json
import re
import sqlite3
from collections import abc
from pathlib import Path

from ...codex import utils
from ...log import get_logger

VERSION = 10
DESCRIPTION = "Name Codex channels by the full thread id"
_log = get_logger(__name__)

_SHORT = len("codex:") + 8
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_KEYED_BY_CHANNEL = ("pins", "session_emoji", "session_briefs")


def _thread_id(channel: str, fields: dict) -> str:
    session_path = fields.get("session_path")
    if isinstance(session_path, str) and (match := _UUID.search(session_path.rsplit("/", 1)[-1])):
        return match.group(0)

    for key in ("session_id", "thread_id"):
        value = fields.get(key)
        if isinstance(value, str) and len(value) > 8 and value.startswith(channel[len("codex:") :]):
            return value

    return ""


def _rollouts(sessions: Path) -> dict[str, Path]:
    if not sessions.exists():
        return {}

    return {
        thread: path
        for path in sessions.rglob("*.jsonl")
        if (thread := utils.extract_session_id_from_filename(path.name))
    }


def _root(thread: str, rollouts: abc.Mapping[str, Path]) -> str:
    """The thread a subagent or approval reviewer runs inside, else *thread*."""
    meta = utils.read_session_meta(rollouts[thread]) if thread in rollouts else None
    if not meta or not utils.is_spawned_thread(meta):
        return thread

    root = meta.get("session_id") or meta.get("parent_thread_id")
    return root if isinstance(root, str) and root else thread


def _fields(metadata: str | None) -> dict:
    try:
        fields = json.loads(metadata or "{}")
    except json.JSONDecodeError:
        return {}

    return fields if isinstance(fields, dict) else {}


def migrate(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, channel, metadata FROM notifications"
        " WHERE channel LIKE 'codex:%' AND length(channel) = ? ORDER BY created_at, id",
        (_SHORT,),
    ).fetchall()
    rollouts = _rollouts(utils.get_sessions_root()) if rows else {}
    newest: dict[str, str] = {}
    moved: set[str] = set()
    for row_id, channel, metadata in rows:
        fields = _fields(metadata)
        thread = _thread_id(channel, fields)
        root = _root(thread, rollouts) if thread else ""
        if root != thread and root.startswith(channel[len("codex:") :]):
            fields = {k: v for k, v in fields.items() if k not in ("session_path", "thread_id")}
            if root in rollouts:
                fields["session_path"] = str(rollouts[root])
            thread = root
        newest[channel] = f"codex:{thread}" if thread else ""
        if not thread:
            continue

        conn.execute(
            "UPDATE notifications SET channel = ?, metadata = ? WHERE id = ?",
            (f"codex:{thread}", json.dumps({**fields, "session_id": thread}), row_id),
        )
        moved.add(f"codex:{thread}")

    for full in moved:
        cursor = conn.execute(
            "UPDATE notifications SET status = 'archived' WHERE channel = ? AND id != ("
            " SELECT id FROM notifications WHERE channel = ? ORDER BY created_at DESC, id DESC LIMIT 1)",
            (full, full),
        )
        if cursor.rowcount:
            _log.info(
                "archive channel=%s reason=migration-codex-channel-duplicates rows=%d",
                full,
                cursor.rowcount,
            )

    for table in _KEYED_BY_CHANNEL:
        for short, full in newest.items():
            if full:
                conn.execute(
                    f"UPDATE OR IGNORE {table} SET channel = ? WHERE channel = ?", (full, short)
                )
                conn.execute(f"DELETE FROM {table} WHERE channel = ?", (short,))
