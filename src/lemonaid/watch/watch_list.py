"""Per-actor watch lists: the docs one actor's waiter watches.

An actor is whoever one delivery adapter wakes (an OpenClaw session, a Codex thread, a
Claude session). Its list is a JSON file mapping each doc's absolute path to the time of
its last event; launchers add and remove docs, and the actor's waiter re-reads the list on
every pass, so the list changes without restarting anything.

Every read-modify-write holds an exclusive flock on `<list>.lock`. The waiter holds a
second flock, `<list>.waiter`, for as long as it runs, and releases it while holding the
list lock when it exits on an empty list; a launcher that finds `.waiter` free while
holding the list lock therefore knows it must start a waiter.
"""

import contextlib
import fcntl
import json
import os
import pathlib
import time
import typing as ty
from collections import abc


def default_lists_dir() -> pathlib.Path:
    """Shared with the standalone watch-doc; `LEMONAID_WATCH_LISTS_DIR` moves it for tests and the sandbox."""
    return pathlib.Path(
        os.environ.get("LEMONAID_WATCH_LISTS_DIR")
        or pathlib.Path.home() / ".local/state/watch-doc/lists"
    )


@contextlib.contextmanager
def _locked(list_path: pathlib.Path) -> abc.Iterator[None]:
    list_path.parent.mkdir(parents=True, exist_ok=True)
    with list_path.with_suffix(".lock").open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def _read(list_path: pathlib.Path) -> dict[str, float]:
    try:
        return {str(k): float(v) for k, v in json.loads(list_path.read_text()).items()}
    except (OSError, ValueError):
        return {}


def _write(list_path: pathlib.Path, docs: abc.Mapping[str, float]) -> None:
    tmp = list_path.with_suffix(f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(dict(sorted(docs.items())), indent=1))
    tmp.replace(list_path)


def _try_flock(path: pathlib.Path) -> ty.IO[str] | None:
    f = path.open("a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


def read(list_path: pathlib.Path) -> dict[str, float]:
    with _locked(list_path):
        return _read(list_path)


def add(list_path: pathlib.Path, doc: pathlib.Path) -> bool:
    """Add or refresh `doc`; True if no waiter holds this list, so the caller must start one."""
    with _locked(list_path):
        _write(list_path, {**_read(list_path), str(doc.resolve()): time.time()})
        probe = _try_flock(list_path.with_suffix(".waiter"))
        if probe is None:
            return False

        probe.close()
        return True


def remove(list_path: pathlib.Path, doc: pathlib.Path) -> bool:
    """True if `doc` was on the list."""
    with _locked(list_path):
        docs = _read(list_path)
        if docs.pop(str(doc.resolve()), None) is None:
            return False

        _write(list_path, docs)
        return True


def touch(list_path: pathlib.Path, doc: pathlib.Path) -> None:
    """Record an event on `doc` now, restarting its idle window; a doc removed meanwhile stays removed."""
    with _locked(list_path):
        docs = _read(list_path)
        if str(doc) in docs:
            _write(list_path, {**docs, str(doc): time.time()})


def expire(list_path: pathlib.Path, idle_seconds: float) -> list[str]:
    """Drop docs with no event for `idle_seconds`; the dropped paths."""
    with _locked(list_path):
        docs = _read(list_path)
        now = time.time()
        stale = [d for d, t in docs.items() if now - t > idle_seconds]
        if stale:
            _write(list_path, {d: t for d, t in docs.items() if d not in stale})
        return stale


def hold_waiter(list_path: pathlib.Path) -> ty.IO[str] | None:
    """The waiter lock for this list, held until released or the process exits; None if another waiter has it."""
    list_path.parent.mkdir(parents=True, exist_ok=True)
    return _try_flock(list_path.with_suffix(".waiter"))


def release_if_empty(list_path: pathlib.Path, waiter: ty.IO[str]) -> bool:
    """Release the waiter lock if the list is empty; True means the waiter should exit."""
    with _locked(list_path):
        if _read(list_path):
            return False

        waiter.close()
        return True
