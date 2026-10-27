"""Probe the unified waiter without importing the brief or CLI machinery."""

import os
import time
from pathlib import Path

from . import waiter_lock

STALE = 120.0  # seconds a waiter may go without polling before it counts as deaf
_BEAT_EVERY = 10.0


def lock_path(lemon_id: str) -> Path:
    state = Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid").expanduser()
    return state / "cursors" / lemon_id / "wait.lock"


def _beat_path(lemon_id: str) -> Path:
    return lock_path(lemon_id).with_suffix(".beat")


def beat(lemon_id: str) -> None:
    path = _beat_path(lemon_id)
    try:
        age = time.time() - path.stat().st_mtime
        if 0 <= age < _BEAT_EVERY:
            return

    except FileNotFoundError:
        pass

    path.touch()


def silent_for(lemon_id: str) -> float:
    """Seconds since the waiter last polled, counting from when it took its lock if it never has."""
    times = [p.stat().st_mtime for p in (_beat_path(lemon_id), lock_path(lemon_id)) if p.exists()]
    return time.time() - max(times) if times else float("inf")


def deaf(lemon_id: str) -> bool:
    return bool(lemon_id) and waiter_lock.held(lock_path(lemon_id)) and silent_for(lemon_id) > STALE


def is_armed(lemon_id: str, grace: float = 0) -> bool:
    """Whether a waiter holds the lemon's lock and is still polling."""
    deadline = time.monotonic() + grace
    while lemon_id:
        if waiter_lock.held(lock_path(lemon_id)) and silent_for(lemon_id) <= STALE:
            return True
        if time.monotonic() >= deadline:
            break
        time.sleep(0.1)
    return False


def mark_delivering(lemon_id: str) -> None:
    lock_path(lemon_id).with_suffix(".delivering").write_text(lock_path(lemon_id).read_text())


def delivering(lemon_id: str) -> bool:
    try:
        return (
            lock_path(lemon_id).with_suffix(".delivering").read_text()
            == lock_path(lemon_id).read_text()
        )
    except FileNotFoundError:
        return False


def clear_delivery(lemon_id: str) -> None:
    lock_path(lemon_id).with_suffix(".delivering").unlink(missing_ok=True)
