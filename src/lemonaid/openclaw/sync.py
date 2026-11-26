"""Every recent OpenClaw conversation as a lemon, added from outside the session.

A row a session registered itself (`lemons.register`) is never added over or archived as
quiet here, and each such write checks that under the database's write lock, since a session
can register at any moment. Archiving (`archived`) and thread binding (`threads`) follow
OpenClaw for every row, though.
"""

import json
import sqlite3
import subprocess
import time
import types
import typing as ty
from collections import abc

from ..inbox import db, ended
from ..log import get_logger
from . import archived, lemons, sessions, threads

_log = get_logger("openclaw.sync")

CHATS = frozenset({"matrix", "signal", "whatsapp", "telegram", "main"})
DAYS = 90.0  # how recently a conversation was active to be a lemon
_BY = "openclaw sync"
_SYNCED = "openclaw_sync"  # metadata key marking a row this added
_TIMEOUT_SECONDS = 60


class Agent(ty.NamedTuple):
    id: str
    name: str
    workspace: str
    default: bool


def agents(cli: str) -> dict[str, Agent]:
    """OpenClaw's agents by id. Raises `sessions.Unavailable`."""
    try:
        done = subprocess.run(
            [cli, "agents", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise sessions.Unavailable(f"openclaw agents list: {error}") from error

    if done.returncode != 0:
        raise sessions.Unavailable(
            done.stderr.strip() or f"openclaw agents list exited {done.returncode}"
        )

    try:
        listed = json.loads(done.stdout)
    except json.JSONDecodeError as error:
        raise sessions.Unavailable(
            f"openclaw agents list said something other than JSON: {error}"
        ) from error

    return {
        str(each["id"]): Agent(
            str(each["id"]),
            str(each.get("identityName") or each.get("name") or each["id"]),
            str(each.get("workspace") or ""),
            bool(each.get("isDefault")),
        )
        for each in listed
        if isinstance(each, dict) and each.get("id")
    }


def _chat(key: str) -> str:
    parts = key.split(":", 4)
    return parts[2] if len(parts) > 2 else ""


def _name(found: sessions.Session, agent: Agent) -> str:
    if not agent.default:
        return agent.name

    parts = found.key.split(":", 4)
    match parts[2:]:
        case ["matrix", _, room]:
            return f"{agent.name} - room {room.removeprefix('!')[:6]}"
        case [chat, "group", _]:
            return f"{agent.name} - {chat.capitalize()} group"
        case [chat, *_] if chat != "main":
            return f"{agent.name} - {chat.capitalize()}"
        case _:
            return agent.name


def _thread(key: str) -> bool:
    """A thread in a chat is a session of its own, keyed `<the chat's key>:thread:<id>`. The grove
    shows the chat and not its threads, as it shows no Codex subagent."""
    return ":thread:" in key


def conversations(
    found: abc.Mapping[str, sessions.Session], now_ms: int, max_age_ms: int, chats: abc.Set[str]
) -> list[sessions.Session]:
    return [
        each
        for each in found.values()
        if _chat(each.key) in chats
        and not _thread(each.key)
        and now_ms - each.updated_ms < max_age_ms
    ]


def _quieted(row: db.Notification) -> bool:
    return row.is_archived and (row.metadata.get("ended") or {}).get("by") == _BY


def _add(conn: sqlite3.Connection, found: sessions.Session, agent: Agent, front_end: str) -> bool:
    """Whether a row was added or revived. Checked and written under one write lock, which
    `register_working`'s commit releases."""
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    existing = db.get_by_channel(conn, sessions.channel(found.key), unread_only=False)
    if existing and not _quieted(existing):  # someone archived it, or the session registered
        conn.rollback()
        return False

    lemons.register(
        conn, found, "", None, agent.workspace, front_end, _name(found, agent), {_SYNCED: True}
    )
    return True


def _archive_quiet(conn: sqlite3.Connection, kept: abc.Set[str]) -> list[str]:
    """Archive the rows this added whose session isn't kept and that have no brief, checking
    both in the update itself."""
    record = json.dumps(ended.record(ended.ARCHIVED, _BY, "its session is no recent conversation"))
    quiet = [
        channel
        for (channel,) in conn.execute(
            "SELECT channel FROM notifications WHERE channel LIKE ? AND status != 'archived'",
            (sessions.PREFIX + "%",),
        ).fetchall()
        if sessions.session_key(channel) not in kept
    ]
    archived = [
        channel
        for channel in quiet
        if conn.execute(
            "UPDATE notifications SET status = 'archived',"
            " metadata = json_set(metadata, '$.ended', json(?))"
            " WHERE channel = ? AND status != 'archived'"
            " AND json_extract(metadata, '$." + _SYNCED + "')"
            " AND NOT EXISTS (SELECT 1 FROM session_briefs b WHERE b.channel = notifications.channel)",
            (record, channel),
        ).rowcount
    ]
    conn.commit()
    return archived


def sync(
    conn: sqlite3.Connection,
    keep: abc.Iterable[sessions.Session],
    by_id: abc.Mapping[str, Agent],
    front_end: str,
    shelved: abc.Mapping[str, str],
    found: abc.Mapping[str, sessions.Session],
    running: abc.Mapping[str, threads.Thread] = types.MappingProxyType({}),
) -> tuple[list[str], list[str]]:
    """*shelved* maps OpenClaw's archived sessions to its reason, and *running* each session id
    to its Codex thread. Returns (added, archived) channels."""
    chats = {key: each for key, each in found.items() if not _thread(key)}  # no thread comes back
    gone, restored = archived.follow(conn, shelved, chats)
    keep = [each for each in keep if each.key not in shelved]
    added = [
        sessions.channel(each.key)
        for each in keep
        if each.agent_id in by_id and _add(conn, each, by_id[each.agent_id], front_end)
    ]
    archived.reported(conn, chats.values(), set(added))
    threads.bind(conn, chats.values(), running)
    quiet = _archive_quiet(conn, {each.key for each in keep})
    _log.info(
        "synced OpenClaw sessions: %d added, %d restored, %d archived in OpenClaw, %d quiet",
        len(added),
        len(restored),
        len(gone),
        len(quiet),
    )
    return added + restored, gone + quiet


def refresh(
    cli: str, max_age_days: float, chats: abc.Set[str], front_end: str
) -> tuple[list[str], list[str]]:
    """`sync` against what the gateway lists now. Raises `sessions.Unavailable`."""
    found, by_id, shelved = sessions.listed(cli), agents(cli), sessions.archived(cli)
    keep = conversations(found, int(time.time() * 1000), int(max_age_days * 86_400_000), chats)
    with db.connect() as conn:
        return sync(conn, keep, by_id, front_end, shelved, found, threads.running(threads.STATE_DB))
