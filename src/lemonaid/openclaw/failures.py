"""OpenClaw turns that failed, kept on disk for each session's lemon page. The gateway keeps no
record of a turn that failed before its lemon wrote anything, so its conversation alone would
show the lemon saying nothing.

`<lemonaid state dir>/openclaw-failures/<session key digest>.jsonl` holds one failure per line,
oldest first: `{"run": ..., "at_ms": ..., "why": ...}`.
"""

import contextlib
import fcntl
import hashlib
import json
import os
import typing as ty
from collections import abc
from pathlib import Path

from ..log import get_logger

_log = get_logger("openclaw.failures")

_KEPT = 5  # failed turns kept for each session


class Failure(ty.NamedTuple):
    at_ms: int
    why: str


def _path(session_key: str) -> Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    digest = hashlib.sha1(session_key.encode()).hexdigest()[:16]
    return Path(state).expanduser() / "openclaw-failures" / f"{digest}.jsonl"


def _entries(path: Path) -> abc.Iterator[dict]:
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return

    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            _log.warning("skipping a line of %s that isn't JSON", path)
            continue
        if isinstance(entry, dict):
            yield entry


@contextlib.contextmanager
def _locked(path: Path) -> abc.Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.with_suffix(".lock")).open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def record(session_key: str, run: str, at_ms: int, why: str) -> None:
    """Keep the session's failed *run*; a retry of a run already kept changes nothing."""
    path = _path(session_key)
    with _locked(path):
        kept = list(_entries(path))
        if run and any(entry.get("run") == run for entry in kept):
            return

        kept = [*kept, {"run": run, "at_ms": at_ms, "why": why}][-_KEPT:]
        temporary = path.with_suffix(".tmp")
        temporary.write_text("".join(json.dumps(entry) + "\n" for entry in kept))
        temporary.replace(path)


def read(session_key: str) -> list[Failure]:
    """The session's failed turns, oldest first."""
    return [
        Failure(int(entry.get("at_ms") or 0), str(entry.get("why") or ""))
        for entry in _entries(_path(session_key))
    ]
