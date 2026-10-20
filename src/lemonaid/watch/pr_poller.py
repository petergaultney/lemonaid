"""One reader per machine for every PR its lemons watch, leaving each PR's snapshot in a file.

Lemons watching the same PRs would otherwise each read them from GitHub every interval. A
PR scout marks its interest (`interested`) and reads `snapshot`. Every unified watcher
starts the poller thread (`ensure_running`), and the one holding its lock reads all PRs
of recent interest each minute in one cheap query (pr_changes), re-reading in full only a
PR that changed, has checks still running, or was last read `_REFRESH` ago.

A snapshot file's mtime is when the poller last confirmed it current. A scout that finds
it missing or older than `_STALE` reads GitHub itself, so a dead or paused poller costs
only the savings; the next watcher to try the lock takes over within a minute.
"""

import json
import os
import threading
import time
from pathlib import Path

from ..log import get_logger
from . import cursors, github_api, pr_activity, pr_changes, waiter_lock

_INTERVAL = 60.0
_INTEREST = 300.0  # a scout polls at least this often while it watches
_REFRESH = 900.0
_STALE = 3 * _INTERVAL
_FORGET = 86400.0  # interest files older than this are removed

_log = get_logger("watch.pr_poller")
_start = threading.Lock()
_started = threading.Event()


def _snapshot_path(repo: str, number: int) -> Path:
    return github_api.state_dir() / "pr" / repo / f"{number}.json"


def _interest_root() -> Path:
    return github_api.state_dir() / "interest"


def interested(repo: str, number: int, watcher: str) -> None:
    path = _interest_root() / repo / str(number) / watcher
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def snapshot(repo: str, number: int) -> dict | None:
    """The PR's `repository` as the poller last confirmed it; None when missing or stale."""
    path = _snapshot_path(repo, number)
    try:
        if time.time() - path.stat().st_mtime > _STALE:
            return None

        return json.loads(path.read_text())["repository"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def read(repo: str, number: int) -> dict | None:
    """The poller's snapshot while it is current, else a read from GitHub."""
    return snapshot(repo, number) or pr_activity.read(repo, number)


def _wanted(now: float) -> set[pr_changes.Key]:
    wanted = set()
    for path in _interest_root().glob("*/*/*/*"):
        try:
            age = now - path.stat().st_mtime
        except FileNotFoundError:
            continue

        if age > _FORGET:
            path.unlink(missing_ok=True)
        elif age < _INTEREST and path.parent.name.isdigit():
            wanted.add((f"{path.parents[2].name}/{path.parents[1].name}", int(path.parent.name)))
    return wanted


def _current(path: Path, fingerprint: str, now: float) -> bool:
    """Whether the saved snapshot still stands: same fingerprint, recent, and no checks running."""
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return False

    return (
        saved.get("fingerprint") == fingerprint
        and now - float(saved.get("fetched", 0)) < _REFRESH
        and not any(
            c.outcome == "pending" for c in pr_activity.parse(saved["repository"], ()).checks
        )
    )


def _cycle(now: float) -> None:
    for (repo, number), fingerprint in pr_changes.fingerprints(_wanted(now)).items():
        path = _snapshot_path(repo, number)
        if _current(path, fingerprint, now):
            os.utime(path)
            continue

        r = pr_activity.read(repo, number)
        if r is not None:
            cursors.write_json(path, {"fingerprint": fingerprint, "fetched": now, "repository": r})


def _run() -> None:
    lock_path = github_api.state_dir() / "pr-poller.lock"
    lock = None
    while True:
        time.sleep(_INTERVAL)  # this watcher's scouts make the first reads themselves
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock = lock or waiter_lock.acquire(lock_path, grace=0)
            if lock:
                _cycle(time.time())
        except Exception:  # the thread's top level: a dead poller would hold its lock
            _log.exception("PR poller cycle failed")


def ensure_running() -> None:
    with _start:
        if _started.is_set():
            return

        _started.set()
    threading.Thread(target=_run, name="pr-poller", daemon=True).start()
