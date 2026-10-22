"""An append-only record of who opened, tossed, or was refused a toss of a place.

One JSON object per line in `places.log` under the state directory. When the file
passes `_MAX_BYTES` it is renamed to `places.log.1`, replacing the previous
rotation, so two files hold at most about twice that.
"""

import contextlib
import json
import os
import sqlite3
import subprocess
from collections import abc
from datetime import datetime
from pathlib import Path

from ..brief import identity, lemon
from ..inbox import db
from ..log import get_logger

_log = get_logger("places.audit")

_MAX_BYTES = 1_000_000
_PS_TIMEOUT_SECONDS = 2
_DB_TIMEOUT_SECONDS = 0.2


def log_path() -> Path:
    state = Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid")

    return state.expanduser() / "logs" / "places.log"


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


def _lemon_id() -> str:
    """The Brief-ID attached to the caller's session, looked up without writing anything.

    A read-only connection with a short timeout keeps a toss from waiting behind a
    database writer, and from claiming or registering briefs just to label an event.
    """
    try:
        with contextlib.closing(
            sqlite3.connect(
                f"file:{db.get_db_path()}?mode=ro", uri=True, timeout=_DB_TIMEOUT_SECONDS
            )
        ) as conn:
            conn.row_factory = sqlite3.Row

            return identity.by_channel(conn).get(lemon.self_channel(conn), "")
    except (LookupError, ValueError, OSError, sqlite3.Error):
        return ""


def caller() -> dict[str, str | int]:
    """The calling lemon's Brief-ID if it has one, else its parent process; always the pid."""
    ppid = os.getppid()
    parent = Path(_ps(ppid, "comm")).name

    return {
        "who": _lemon_id() or parent or "unknown",
        "pid": os.getpid(),
        "parent": parent,
        "tty": _ps(os.getpid(), "tty"),
    }


def _rotate(path: Path) -> None:
    if path.exists() and path.stat().st_size > _MAX_BYTES:
        path.replace(path.with_name(path.name + ".1"))


def record(
    action: str,
    outcome: str,
    key: str = "",
    directory: str = "",
    session: str = "",
    flags: abc.Sequence[str] = (),
    reason: str = "",
) -> None:
    """Append one event; a failure to write is logged and never stops the action itself."""
    try:
        entry = {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "action": action,
            "outcome": outcome,
            "key": key,
            "dir": directory,
            "session": session,
            "flags": list(flags),
            "reason": reason,
            **caller(),
        }
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate(path)
        with path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except (OSError, ValueError) as e:
        _log.warning("could not write the place audit log: %s", e)


def _read_file(path: Path) -> abc.Iterator[dict]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return

    for line in lines:
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            _log.warning("skipping a malformed line in %s", path)


def entries(limit: int, key: str = "") -> list[dict]:
    """The last *limit* events, oldest first, optionally only those naming *key* (or session *key*)."""
    path = log_path()
    found = [
        e
        for file in (path.with_name(path.name + ".1"), path)
        for e in _read_file(file)
        if not key or key in (e.get("key"), e.get("session"))
    ]

    return found[-limit:] if limit > 0 else found
