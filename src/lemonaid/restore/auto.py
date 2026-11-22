"""Restore starting by itself: one run at a time, and the inbox row that asks for it.

A trigger (tmux.conf's line at server start, or the inbox noticing lost lemons) runs the
same `lemonaid restore` a person would, with `--auto`, which reads `[restore] auto`:
`off` does nothing, `ask` leaves one inbox row to restore or dismiss them from, `on`
restores at once. A lock makes two triggers, or a trigger and a person, one run.
"""

import contextlib
import fcntl
import os
import pathlib
import sqlite3
import subprocess
import time
from collections import abc

from ..inbox import db, ended
from ..log import LOG_PATH
from . import loss, report

ASK_CHANNEL = "lemonaid:restore-lost"
_LOCK_TRIES = 20
_LOCK_PAUSE_SECONDS = 0.05


def _lock_path() -> pathlib.Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return pathlib.Path(state).expanduser() / "restore.lock"


@contextlib.contextmanager
def lock() -> abc.Iterator[bool]:
    """Whether this process holds the restore lock, for as long as the block runs.

    It tries for about a second, since `running` takes the lock shared for an instant.
    """
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as held:
        for _ in range(_LOCK_TRIES):
            try:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(_LOCK_PAUSE_SECONDS)
        else:
            yield False
            return

        yield True


def running() -> bool:
    """Whether a restore holds its lock now, and may still start any lost lemon."""
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as probe:
        try:
            fcntl.flock(probe, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True

        fcntl.flock(probe, fcntl.LOCK_UN)
        return False


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


def _restoring(lost: abc.Sequence[db.Notification]) -> str:
    return f"Restoring {len(lost)} lemons lost with their terminal at {_when(lost)}"


def restoring(conn: sqlite3.Connection, lost: abc.Sequence[db.Notification]) -> None:
    """Show, in the same row, that a restore is under way."""
    if lost:
        db.add(conn, ASK_CHANNEL, _restoring(lost) + "...", name="restore", status="read")


def counter(
    lost: abc.Sequence[db.Notification],
) -> abc.Callable[[report.Placed | report.Result], None]:
    """Count each lemon restore is through with in that row: how many are back, and that
    selecting one still lost starts it next."""
    back = failed = 0

    def count(each: report.Placed | report.Result) -> None:
        nonlocal back, failed
        if isinstance(each, report.Result) and each.outcome == report.NOT_RESTORED:
            failed += 1
        else:
            back += 1
        with db.connect() as conn:
            db.update_message(
                conn,
                ASK_CHANNEL,
                f"{_restoring(lost)}: {back} back"
                + (f", {failed} not restored" if failed else "")
                + ". Select a lemon still lost to have it started next.",
            )

    return count


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
