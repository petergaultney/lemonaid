"""Restore starting by itself: one run at a time, and the inbox row that asks for it.

A trigger (tmux.conf's line at server start, or the inbox noticing lost lemons) runs the
same `lemonaid restore` a person would, with `--auto`, which reads `[restore] auto`:
`off` does nothing, `ask` leaves one inbox row to restore or dismiss them from, `on`
restores at once. A lock makes two triggers, or a trigger and a person, one run.
"""

import contextlib
import fcntl
import pathlib
import sqlite3
import subprocess
import time
from collections import abc

from ..inbox import db, ended
from ..log import LOG_PATH
from ..watch import cursors
from . import loss

ASK_CHANNEL = "lemonaid:restore-lost"


def _lock_path() -> pathlib.Path:
    return cursors.root().parent / "restore.lock"


@contextlib.contextmanager
def lock() -> abc.Iterator[bool]:
    """Whether this process holds the restore lock, for as long as the block runs."""
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as held:
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return

        yield True


def _when(lost: abc.Sequence[db.Notification]) -> str:
    at = min(float((row.metadata.get(ended.KEY) or {}).get("at") or time.time()) for row in lost)
    return time.strftime("%H:%M", time.localtime(at))


def ask(conn: sqlite3.Connection, lost: abc.Sequence[db.Notification]) -> None:
    """Leave the row that asks to restore or dismiss *lost*, or take it away when none are."""
    if not lost:
        clear(conn)
        return

    db.add(
        conn,
        ASK_CHANNEL,
        f"{len(lost)} lemons were lost with their terminal at {_when(lost)}. "
        "Select this row to restore them or dismiss them.",
        name="restore",
    )


def restoring(conn: sqlite3.Connection, lost: abc.Sequence[db.Notification]) -> None:
    """Show, in the same row, that a restore is under way."""
    if lost:
        db.add(
            conn,
            ASK_CHANNEL,
            f"Restoring {len(lost)} lemons lost with their terminal at {_when(lost)}...",
            name="restore",
            status="read",
        )


def clear(conn: sqlite3.Connection) -> None:
    db.archive_channel(conn, ASK_CHANNEL, "nothing lost", cause=ended.ARCHIVED, by="restore")


def due(conn: sqlite3.Connection, setting: str, looking: bool) -> bool:
    """*looking* is the caller's own judgment that now is a time to check: the inbox
    starting, or finding lemons newly lost, rather than every watcher pass."""
    return (
        setting != "off"
        and looking
        and any(ended.lost(row.metadata) for row in loss.candidates(conn))
    )


def trigger() -> None:
    """Start `lemonaid restore --auto` in the background, detached from the caller."""
    with open(LOG_PATH, "a") as log:
        subprocess.Popen(
            ["lemonaid", "restore", "--auto"],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
