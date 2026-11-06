"""The messages Codex holds in its own queue, and whether it will start a turn from them.

`codex queue` writes a row to `queued_items` in `queue_1.sqlite` in the Codex home and exits
0 for any stored thread, loaded or not. A Codex process that has the thread loaded starts a
turn from the oldest row once the thread is idle, and deletes the row as the turn starts. It
looks for rows that another process wrote every 10 seconds. It starts none after an Esc
interrupt until its user's next turn completes. The database is Codex's own and has no
documentation: its table and columns are read from Codex 0.166.0's source. lemonaid queries
it through a short-lived read-only connection using SQLite's normal WAL coordination.
"""

import contextlib
import sqlite3
import typing as ty
from pathlib import Path

from .. import auto_read
from ..lemon_watchers import watcher as lemon_watcher  # a module: it imports this one, via tmux
from ..log import get_logger

_log = get_logger("codex.queued")

UNRUN_AFTER_SECONDS = 60.0  # six of Codex's 10-second looks for new rows
_READ_TIMEOUT_SECONDS = 1.0


class Held(ty.NamedTuple):
    count: int
    since: float  # when Codex took the oldest of them, in seconds since the epoch


class TurnEnd(ty.NamedTuple):
    at: float
    interrupted: bool  # an Esc interrupt ended it


def held(home: Path) -> dict[str, Held]:
    """Read Codex's live queue without SQL writes; SQLite may update WAL sidecars."""
    path = home / "queue_1.sqlite"
    if not path.is_file():
        return {}

    try:
        with contextlib.closing(
            sqlite3.connect(
                f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=_READ_TIMEOUT_SECONDS
            )
        ) as conn:
            rows = conn.execute(
                "SELECT thread_id, COUNT(*), MIN(created_at_ms) FROM queued_items GROUP BY thread_id"
            ).fetchall()
        return {thread: Held(count, oldest / 1000) for thread, count, oldest in rows}
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        _log.warning(
            "cannot read Codex's queue in %s; held-message detection unavailable "
            "(the queue schema may have changed): %s",
            path,
            error,
        )
        return {}


def last_turn_end(rollout: Path) -> TurnEnd | None:
    """How the thread's last turn ended; None while a turn is open or the rollout's tail doesn't say."""
    for entry in auto_read.newest_first(lemon_watcher.read_jsonl_tail(rollout)):
        payload = entry.get("payload")
        if entry.get("type") != "event_msg" or not isinstance(payload, dict):
            continue

        if payload.get("type") == "task_started":
            return None

        if payload.get("type") in ("task_complete", "turn_aborted"):
            at = lemon_watcher.parse_timestamp(entry.get("timestamp", ""))
            interrupted = (
                payload["type"] == "turn_aborted" and payload.get("reason") == "interrupted"
            )
            return TurnEnd(at, interrupted) if at is not None else None

    return None


def _count(found: Held) -> str:
    return "a queued message" if found.count == 1 else f"{found.count} queued messages"


def unrun(found: Held, end: TurnEnd | None, now: float) -> str:
    """Why the thread's lemon will not read *found*, or "" while Codex may still start a turn from it.

    A message waits while a turn runs and starts within seconds of its end, so only one
    that has waited `UNRUN_AFTER_SECONDS` since both its queueing and the last turn's end
    counts. *end* is None while a turn is open.
    """
    if end is None:
        return ""

    waited = now - max(found.since, end.at)
    if waited < UNRUN_AFTER_SECONDS:
        return ""

    if end.interrupted:
        return (
            f"an interrupt (Esc) ended its last turn, so Codex starts no turn from "
            f"{_count(found)} until its user's next prompt"
        )

    minutes = int(waited // 60)
    return (
        f"Codex has held {_count(found)} for {minutes} minute{'' if minutes == 1 else 's'} "
        "on an idle thread and started no turn"
    )
