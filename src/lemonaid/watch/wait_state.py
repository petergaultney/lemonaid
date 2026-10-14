"""Probe the unified waiter without importing the brief or CLI machinery."""

import os
import time
from pathlib import Path

from . import waiter_lock


def lock_path(lemon_id: str) -> Path:
    state = Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid").expanduser()
    return state / "cursors" / lemon_id / "wait.lock"


def is_armed(lemon_id: str, grace: float = 0) -> bool:
    deadline = time.monotonic() + grace
    while lemon_id:
        if waiter_lock.held(lock_path(lemon_id)):
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
