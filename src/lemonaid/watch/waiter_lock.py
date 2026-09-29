"""The lock a waiter holds for as long as it runs, so a second waiter for the same thing refuses to start."""

import fcntl
import os
import pathlib
import sys
import time
import typing as ty


def lock_holder(lock_path: pathlib.Path) -> str:
    try:
        return lock_path.read_text().strip() or "unknown process"
    except OSError:
        return "unknown process"


def acquire(lock_path: pathlib.Path) -> ty.IO[str] | None:
    """The open lock file (held until this process exits), or None if another waiter holds it."""
    f = lock_path.open("a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None

    f.truncate(0)
    f.write(f"pid {os.getpid()} since {time.strftime('%Y-%m-%d %H:%M:%S')}: {' '.join(sys.argv)}\n")
    f.flush()
    return f
