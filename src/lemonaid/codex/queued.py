"""The messages Codex holds in its own queue, and whether it will start a turn from them.

`codex queue` writes a row to `queued_items` in `queue_1.sqlite` in the Codex home and exits
0 for any stored thread, loaded or not. A Codex process that has the thread loaded starts a
turn from the oldest row once the thread is idle, and deletes the row as the turn starts. It
looks for rows that another process wrote every 10 seconds. It starts none after an Esc
interrupt until its user's next turn completes. The database is Codex's own and has no
documentation: its table and columns are read from Codex 0.166.0's source. lemonaid reads
a private copy of it, and writes nothing in the Codex home.
"""

import contextlib
import shutil
import sqlite3
import tempfile
import typing as ty
from pathlib import Path

from .. import auto_read
from ..lemon_watchers import watcher as lemon_watcher  # a module: it imports this one, via tmux
from ..log import get_logger

_log = get_logger("codex.queued")

UNRUN_AFTER_SECONDS = 60.0  # six of Codex's 10-second looks for new rows
_COPY_TRIES = 3


class Held(ty.NamedTuple):
    count: int
    since: float  # when Codex took the oldest of them, in seconds since the epoch


class TurnEnd(ty.NamedTuple):
    at: float
    interrupted: bool  # an Esc interrupt ended it


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        found = path.stat()
    except FileNotFoundError:
        return None

    return found.st_size, found.st_mtime_ns


def _copied(path: Path, into: Path) -> bool:
    """Copy the database at *path* and its WAL into *into*; False if a writer changed them meanwhile.

    To read a WAL database, SQLite writes its `-shm` file, even read-only, and it creates the
    `-shm` and `-wal` files when no other process has them open. A copy keeps the Codex
    home unchanged. SQLite rebuilds the `-shm` file from the copied WAL, up to its last commit.
    """
    sources = [path, path.with_name(f"{path.name}-wal")]
    before = [_stamp(source) for source in sources]
    for source, stamp in zip(sources, before, strict=True):
        if stamp is None:
            (into / source.name).unlink(missing_ok=True)
        else:
            shutil.copyfile(source, into / source.name)
    return [_stamp(source) for source in sources] == before


def held(home: Path) -> dict[str, Held]:
    """The messages Codex holds for each thread; empty when its database can't be read."""
    path = home / "queue_1.sqlite"
    if not path.is_file():
        return {}

    try:
        with tempfile.TemporaryDirectory(prefix="lemonaid-codex-queue-") as into:
            if not any(_copied(path, Path(into)) for _ in range(_COPY_TRIES)):
                _log.warning(
                    "Codex wrote its queue in %s during each of %d copies", path, _COPY_TRIES
                )
                return {}

            with contextlib.closing(sqlite3.connect(Path(into) / path.name, timeout=1)) as conn:
                rows = conn.execute(
                    "SELECT thread_id, COUNT(*), MIN(created_at_ms) FROM queued_items GROUP BY thread_id"
                ).fetchall()
    except (OSError, sqlite3.Error) as error:
        _log.warning("cannot read Codex's queue in %s: %s", path, error)
        return {}

    return {thread: Held(count, oldest / 1000) for thread, count, oldest in rows}


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
