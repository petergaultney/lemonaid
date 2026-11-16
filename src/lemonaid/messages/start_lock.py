"""One start of a lemon at a time, whoever starts it.

`lemon resume`, `tell`'s autoresume and restore each hold this from their last check
that the lemon isn't running or starting through launching it. The resumes record the
start in its start log (`resume_log`) before letting go, which restore reads; restore
holds its own lock until the lemon is proven running, which the resumes check.

The holder writes its pid and command line into the lock file, which is true only while
the file is locked: a start that has to wait logs who it waits for.
"""

import contextlib
import fcntl
import hashlib
import os
import sys
from collections import abc
from pathlib import Path

from ..inbox import db
from ..log import get_logger

_log = get_logger("messages.start_lock")


def _path(channel: str) -> Path:
    return (
        db.get_db_path().parent
        / "starting"
        / f"{hashlib.sha256(channel.encode()).hexdigest()}.lock"
    )


@contextlib.contextmanager
def held(channel: str) -> abc.Iterator[None]:
    path = _path(channel)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _log.info("waiting to start %s: %s holds its start lock", channel, holder(channel))
            fcntl.flock(lock, fcntl.LOCK_EX)
        lock.truncate(0)
        lock.write(f"pid {os.getpid()}: {' '.join([Path(sys.argv[0]).name, *sys.argv[1:]])}\n")
        lock.flush()
        try:
            yield
        finally:
            lock.truncate(0)  # so the next holder's line is never read as an earlier one's


def holder(channel: str) -> str:
    """Who holds *channel*'s start lock, as it wrote itself down; "" when nobody does."""
    try:
        lock = _path(channel).open()
    except FileNotFoundError:
        return ""

    with lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return lock.read().strip() or "an unknown process"

        return ""
