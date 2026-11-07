"""Who is running this lemonaid process, from evidence that costs no writes.

The first source that names someone wins, and `via` records which one it was:

- `code`: lemonaid names the actor itself, for its own background jobs (`LEMONAID_ACTOR`,
  or a caller passing one, such as the inbox watcher).
- `env`: the harness's session variables (`LEMONAID_CHANNEL`, `CLAUDE_CODE_SESSION_ID`,
  `CODEX_THREAD_ID`) name a channel. The actor is that channel's Brief-ID, else the channel.
- `tmux`: the inbox records a lemon in the tmux pane this process runs in, and a harness
  process is among this one's ancestors. A person's command in that pane, after the lemon
  was suspended or exited, has no harness ancestor and falls through to `tty`.
- `tty`: a terminal on stdin and none of the above, so a person: their login name.
- `ppid`: nothing else; the parent process's name, or "unknown".

A lemonaid process started by a lemon inherits that lemon's environment, so a background
job that acts for lemonaid rather than for that lemon must set `LEMONAID_ACTOR`.
"""

import contextlib
import getpass
import os
import sqlite3
import subprocess
from pathlib import Path

from ..brief import identity, lemon
from ..inbox import db, self_session
from ..inbox.channel import channel_id
from ..launch.restart import process
from ..log import get_logger
from ..messages import recipient

_log = get_logger("audit.actor")

ACTOR_ENV = "LEMONAID_ACTOR"
_HARNESS_ENV = ("LEMONAID_CHANNEL", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")
_PS_TIMEOUT_SECONDS = 2
_DB_TIMEOUT_SECONDS = 0.2


def _ps(pid: int, field: str) -> str:
    try:
        result = subprocess.run(
            ["ps", "-o", f"{field}=", "-p", str(pid)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    return result.stdout.strip()


def _harness_channel(conn: sqlite3.Connection) -> str:
    if not any(os.environ.get(name) for name in _HARNESS_ENV):
        return ""

    return lemon.self_channel(conn)  # with one of these set, it never asks tmux


def _under_harness() -> bool:
    try:
        return any(recipient.is_harness(p.executable) for p in process.ancestry(os.getppid()))
    except (OSError, subprocess.SubprocessError) as e:
        _log.info("could not read this process's ancestry: %s", e)
        return False


def _pane_channel(conn: sqlite3.Connection) -> str:
    pane = os.environ.get("TMUX_PANE", "")
    where = self_session.pane_location(pane) if pane and _under_harness() else None
    if where is None:
        return ""

    return self_session.resolve(conn, where)[0]


def _lemon(conn: sqlite3.Connection) -> tuple[str, str, str]:
    """(who, via, channel) for a lemon, or ("", "", "") when no lemon is found."""
    for via, find in (("env", _harness_channel), ("tmux", _pane_channel)):
        if channel := find(conn):
            return identity.by_channel(conn).get(channel, "") or channel, via, channel

    return "", "", ""


def _env_channel() -> str:
    """The channel the harness's environment names, worked out without the database."""
    if channel := os.environ.get("LEMONAID_CHANNEL"):
        return channel

    if session_id := os.environ.get("CLAUDE_CODE_SESSION_ID"):
        return channel_id("claude", session_id)

    thread = os.environ.get("CODEX_THREAD_ID")
    return f"codex:{thread}" if thread else ""


def _lemon_read_only() -> tuple[str, str, str]:
    """`_lemon`, through a read-only connection with a short timeout.

    An audited action never waits behind a database writer, and never claims or registers
    a brief just to label an event.
    """
    try:
        with contextlib.closing(
            sqlite3.connect(
                f"file:{db.get_db_path()}?mode=ro", uri=True, timeout=_DB_TIMEOUT_SECONDS
            )
        ) as conn:
            conn.row_factory = sqlite3.Row
            return _lemon(conn)
    except (LookupError, ValueError, OSError, sqlite3.Error) as e:
        _log.info("could not look the calling lemon up: %s", e)
        channel = _env_channel()
        return channel, "env" if channel else "", channel


def _person() -> str:
    try:
        return getpass.getuser() if os.isatty(0) else ""
    except OSError:
        return ""


def caller(by: str = "") -> dict[str, str | int]:
    """The actor of this process and the evidence for it; *by* names a lemonaid job outright."""
    pid = os.getpid()
    parent = Path(_ps(os.getppid(), "comm")).name
    evidence: dict[str, str | int] = {"pid": pid, "parent": parent, "tty": _ps(pid, "tty")}
    if named := by or os.environ.get(ACTOR_ENV, ""):
        return {"who": named, "via": "code", "channel": "", **evidence}

    who, via, channel = _lemon_read_only()
    if who:
        return {"who": who, "via": via, "channel": channel, **evidence}

    if person := _person():
        return {"who": person, "via": "tty", "channel": "", **evidence}

    return {"who": parent or "unknown", "via": "ppid", "channel": "", **evidence}
