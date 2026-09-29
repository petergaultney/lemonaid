"""One lock that brief and message writes share, and a migration takes alone.

A write takes the lock shared and checks for the pause while holding it. A
migration writes the pause marker and then takes the lock exclusively, which
waits for every write that got in before the marker, however long it takes
(`tell -` reading a slow stdin, say). Anything after sees the marker and
refuses. Versions of lemonaid from before this lock don't take it; the
migration's source recheck and verification are what catch those.
"""

import contextlib
import fcntl
import os
from collections import abc
from pathlib import Path

from . import layout


class Paused(ValueError):
    pass


def _lock_file() -> Path:
    override = os.environ.get("LEMONAID_STATE_DIR")
    state = Path(override) if override else Path.home() / ".local" / "state" / "lemonaid"
    state.mkdir(parents=True, exist_ok=True)
    return state / "home.lock"


@contextlib.contextmanager
def operation() -> abc.Iterator[None]:
    """Hold the lock shared for one brief or message write; raises `Paused` during a migration."""
    with _lock_file().open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        if paused := layout.paused():
            raise Paused(paused)

        yield


def drain() -> None:
    """Wait until every write that started before the pause has finished."""
    with _lock_file().open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
