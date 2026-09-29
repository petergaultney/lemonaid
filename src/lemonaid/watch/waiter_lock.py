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


def held(lock_path: pathlib.Path) -> bool:
    """Whether a waiter holds the lock. The probe is a shared lock and writes nothing."""
    try:
        f = lock_path.open()
    except FileNotFoundError:
        return False

    with f:
        try:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True

        return False


def acquire(lock_path: pathlib.Path, grace: float = 1.0) -> ty.IO[str] | None:
    """The open lock file (held until this process exits), or None if another waiter holds it.

    Retries for `grace` seconds, which outlasts a `held` probe or a standalone waiter's
    `--status`, both of which lock the file for a moment.
    """
    f = lock_path.open("a+")
    deadline = time.monotonic() + grace
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() < deadline:
                time.sleep(0.05)
                continue

            f.close()
            return None

    f.truncate(0)
    f.write(f"pid {os.getpid()} since {time.strftime('%Y-%m-%d %H:%M:%S')}: {' '.join(sys.argv)}\n")
    f.flush()
    return f
