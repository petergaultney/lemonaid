"""OpenClaw's gateway as a harness: its sessions, from `openclaw sessions --json`.

A session's lemon is named by its session key (`agent:<agent>:<channel>:<kind>:<peer>`),
which outlives the session ids and Codex threads OpenClaw rotates beneath it.
"""

import json
import os
import shutil
import subprocess
import time
import typing as ty
from pathlib import Path

from ..inbox import db
from ..inbox.turns import STALE_SECONDS
from ..log import get_logger
from ..watch import turns
from . import gateway

_log = get_logger("openclaw.sessions")

PREFIX = "openclaw:"
_LIST_TIMEOUT = 60  # the CLI takes about 3 s


class Session(ty.NamedTuple):
    key: str
    session_id: str
    agent_id: str
    kind: str  # direct, group, cron, ...
    status: str  # running, done, failed, ...; "" before its first turn
    updated_ms: int
    total_tokens: int
    context_tokens: int
    interacted_ms: int = 0  # its last message; an archive or other patch moves updated_ms only


class Unavailable(Exception):
    """The gateway's session list could not be read."""


def channel(session_key: str) -> str:
    return PREFIX + session_key


def session_key(channel_: str) -> str:
    return channel_.removeprefix(PREFIX) if channel_.startswith(PREFIX) else ""


def cli() -> str:
    """The `openclaw` executable: on PATH, or where its installer puts it."""
    return shutil.which("openclaw") or str(Path.home() / ".local/bin/openclaw")


def hosted_codex_home() -> Path | None:
    """This process's Codex home when OpenClaw runs it, or None outside OpenClaw.

    OpenClaw runs each agent on its own Codex harness, so a shell command an OpenClaw
    session runs sees `CODEX_THREAD_ID` like any Codex lemon's, but under a Codex home
    inside OpenClaw's agent directory.
    """
    home = os.environ.get("CODEX_HOME", "")
    if not home:
        return None

    agents = Path.home() / ".openclaw" / "agents"
    path = Path(home).expanduser()
    return path if path.is_relative_to(agents) else None


def hosted_agent() -> str:
    """The id of the OpenClaw agent running this process, or "" outside OpenClaw."""
    home = hosted_codex_home()
    parts = home.relative_to(Path.home() / ".openclaw" / "agents").parts if home else ()
    return parts[0] if parts else ""


def _session(entry: dict[str, ty.Any]) -> Session | None:
    key = entry.get("key")
    if not isinstance(key, str) or not key:
        return None

    return Session(
        key=key,
        session_id=str(entry.get("sessionId") or ""),
        agent_id=str(entry.get("agentId") or ""),
        kind=str(entry.get("kind") or ""),
        status=str(entry.get("status") or ""),
        updated_ms=int(entry.get("updatedAt") or 0),
        total_tokens=int(entry.get("totalTokens") or 0),
        context_tokens=int(entry.get("contextTokens") or 0),
        interacted_ms=int(entry.get("lastInteractionAt") or entry.get("updatedAt") or 0),
    )


def _parse(text: str) -> dict[str, Session]:
    """`openclaw sessions --all-agents --json` output, by session key."""
    entries = json.loads(text).get("sessions") or []
    return {found.key: found for entry in entries if (found := _session(entry))}


def listed(executable: str) -> dict[str, Session]:
    """Every session the gateway stores, by session key. Raises `Unavailable`."""
    try:
        cp = subprocess.run(
            [executable, "sessions", "--all-agents", "--limit", "all", "--json"],
            capture_output=True,
            text=True,
            timeout=_LIST_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Unavailable(f"openclaw sessions: {error}") from error

    if cp.returncode != 0:
        raise Unavailable(f"openclaw sessions exited {cp.returncode}: {cp.stderr.strip()[-300:]}")

    try:
        return _parse(cp.stdout)
    except (ValueError, AttributeError) as error:
        raise Unavailable(f"openclaw sessions printed no session list: {error}") from error


def archived(executable: str) -> dict[str, str]:
    """Every archived session's key and the reason OpenClaw gives. Raises `Unavailable`.

    `openclaw sessions` lists archived sessions without saying they are, so this asks the
    gateway's `sessions.list`, which filters on it.
    """
    params = {"archived": True, "limit": 1_000_000}
    try:
        entries = gateway.call(executable, "sessions.list", params, _LIST_TIMEOUT).get("sessions")
    except OSError as error:
        raise Unavailable(f"openclaw sessions.list: {error}") from error

    return {
        str(each["key"]): str(each.get("archiveReason") or "")
        for each in entries or []
        if isinstance(each, dict) and each.get("key")
    }


def exists_checker(executable: str, max_age: float) -> ty.Callable[[str], bool | None]:
    """Whether a session key is still stored, re-listing at most every *max_age* seconds.

    None when the gateway can't say; a scout asks often, and the list takes seconds.
    """
    known: dict[str, Session] | None = None
    listed_at = float("-inf")

    def exists(key: str) -> bool | None:
        nonlocal known, listed_at
        if time.monotonic() - listed_at >= max_age:
            listed_at = time.monotonic()
            try:
                known = listed(executable)
            except Unavailable as error:
                _log.warning("%s", error)
                known = None
        return None if known is None else key in known

    return exists


def recorded_turns(session_key: str) -> turns.Turns:
    """The session's latest turn as `lemonaid openclaw observe` recorded it in the inbox, read
    afresh each time; None where it has recorded none, as when it isn't running."""
    at = channel(session_key)

    def latest() -> turns.Turn | None:
        with db.connect() as conn:
            row = db.get_by_channel(conn, at, unread_only=False)
        if row is None or "turn_started_at" not in row.metadata:
            return None

        return turns.Turn(
            row.turn_at is not None and time.time() - row.turn_at < STALE_SECONDS,
            float(row.metadata["turn_started_at"]),
            float(row.metadata.get("turn_ended_at") or 0),
        )

    return latest
