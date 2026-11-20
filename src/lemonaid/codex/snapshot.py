"""The Codex service's answers in a file, and the threads lemonaid has asked about.

A reader marks each thread it asks about (`interested`), so the service keeps it current.
The snapshot's mtime is when the service last refreshed it; one older than `STALE` is from
a service that has stopped, and its answers are not used.
"""

import json
import os
import re
import tempfile
import time
import typing as ty
from collections import abc
from pathlib import Path

from ..log import get_logger
from . import stored

_log = get_logger("codex.snapshot")

STALE = 300.0
FORGET = 86400.0  # interest older than this is dropped
_THREAD_ID = re.compile(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")  # also a file name

Answers = dict[str, stored.Thread | None]


def _root() -> Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return Path(state).expanduser() / "codex"


def _path() -> Path:
    return _root() / "threads.json"


def _interest() -> Path:
    return _root() / "interest"


def read() -> Answers:
    """The current snapshot, or nothing when the service hasn't refreshed it lately."""
    try:
        if time.time() - _path().stat().st_mtime > STALE:
            return {}

        raw: dict[str, ty.Any] = json.loads(_path().read_text())
    except (OSError, ValueError) as error:
        _log.debug("no Codex snapshot: %s", error)
        return {}

    return {
        thread: None if record is None else stored.Thread(**record)
        for thread, record in raw.items()
    }


def write(answers: Answers) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
        json.dump(
            {t: None if a is None else a._asdict() for t, a in answers.items()},
            f,
            sort_keys=True,
        )
    os.replace(f.name, path)


def interested(threads: abc.Iterable[str]) -> None:
    """Mark *threads* as asked about now."""
    root = _interest()
    try:
        root.mkdir(parents=True, exist_ok=True)
        for thread in threads:
            if _THREAD_ID.fullmatch(thread):
                (root / thread).touch()
    except OSError as error:
        _log.warning("could not record interest in Codex threads: %s", error)


def interest() -> dict[str, float]:
    """Each thread asked about, with when it was last asked (Unix seconds). Threads last
    asked about more than `FORGET` ago are forgotten."""
    asked: dict[str, float] = {}
    now = time.time()
    try:
        entries = list(os.scandir(_interest()))
    except FileNotFoundError:
        return asked

    for entry in entries:
        try:
            when = entry.stat().st_mtime
            if now - when > FORGET:
                os.unlink(entry.path)
            else:
                asked[entry.name] = when
        except FileNotFoundError:
            continue
    return asked
