"""A lock per lemon inbox, held for as long as that lemon's waiter runs.

Only a Claude lemon's own background task can wake it, so the Stop hook asks
whether that task is alive before letting the turn end.
"""

import contextlib
import fcntl
import os
import time
from collections import abc
from pathlib import Path


class AlreadyArmed(Exception):
    pass


def _lock_file(inbox: Path) -> Path:
    return inbox / ".waiter.lock"


@contextlib.contextmanager
def armed(inbox: Path) -> abc.Iterator[None]:
    """Holds the inbox's waiter lock; raises `AlreadyArmed` if another waiter has it."""
    inbox.mkdir(parents=True, exist_ok=True)
    with open(_lock_file(inbox), "a+") as lock:
        deadline = time.monotonic() + 1.0  # outlasts a probe's momentary shared lock
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() < deadline:
                    time.sleep(0.05)
                    continue

                lock.seek(0)
                holder = lock.read().strip() or "unknown"
                raise AlreadyArmed(
                    f"A waiter is already armed for {inbox.name} (pid {holder})"
                ) from None

        lock.truncate(0)
        lock.write(f"{os.getpid()}\n")
        lock.flush()
        yield


def _held(inbox: Path) -> bool:
    try:
        lock = open(_lock_file(inbox))
    except FileNotFoundError:
        return False

    with lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True

        return False


def is_armed(inbox: Path, grace: float = 0.0, interval: float = 0.1) -> bool:
    """Whether a waiter holds the lock, waiting up to `grace` seconds for one to start.

    A lemon typically arms its waiter as the last act of a turn, so the process
    may still be starting when the Stop hook asks.
    """
    deadline = time.monotonic() + grace
    while True:
        if _held(inbox):
            return True

        if time.monotonic() >= deadline:
            return False

        time.sleep(interval)
