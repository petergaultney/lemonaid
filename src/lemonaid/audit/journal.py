"""Append-only JSONL files under the state directory's `logs/`, one object per line.

When a file passes `_MAX_BYTES` it is renamed to `<name>.1`, replacing the previous
rotation, so each log holds at most about twice that. Writers across processes take
`<name>.lock` for the rotation and append, so two cannot both rotate and lose `.1`; one that
waits past `_LOCK_SECONDS` appends without rotating, since a line written with `O_APPEND`
lands whole either way.
"""

import fcntl
import json
import os
import time
from collections import abc
from pathlib import Path

from ..log import get_logger

_log = get_logger("audit.journal")

_MAX_BYTES = 1_000_000
_LOCK_SECONDS = 1.0
_LOCK_POLL_SECONDS = 0.01


def path(name: str) -> Path:
    state = Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid")

    return state.expanduser() / "logs" / name


def _rotated(current: Path) -> Path:
    return current.with_name(current.name + ".1")


def _locked(fd: int) -> bool:
    deadline = time.monotonic() + _LOCK_SECONDS
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return False

            time.sleep(_LOCK_POLL_SECONDS)


def append(name: str, entry: abc.Mapping) -> None:
    """A failure to write is logged and never raised: recording never stops the action."""
    try:
        line = json.dumps(entry) + "\n"
        current = path(name)
        current.parent.mkdir(parents=True, exist_ok=True)
        with open(current.with_name(name + ".lock"), "a") as lock:
            held = _locked(lock.fileno())
            if not held:
                _log.warning("appending to %s without rotating: its lock is held", name)
            elif current.exists() and current.stat().st_size > _MAX_BYTES:
                current.replace(_rotated(current))
            with current.open("a") as f:
                f.write(line)  # closing the lock file releases the lock
    except (OSError, ValueError, TypeError) as e:
        _log.warning("could not write the audit log %s: %s", name, e)


def _lines(file: Path) -> abc.Iterator[dict]:
    try:
        lines = file.read_text().splitlines()
    except OSError:
        return

    for line in lines:
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            _log.warning("skipping a malformed line in %s", file)


def read(name: str) -> abc.Iterator[dict]:
    """Every entry in *name*, oldest first, starting with its rotated file."""
    current = path(name)
    for file in (_rotated(current), current):
        yield from _lines(file)
