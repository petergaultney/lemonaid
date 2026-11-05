"""One reader per machine for every PR its lemons watch, leaving each PR's snapshot in a file.

Lemons watching the same PRs would otherwise each read them from GitHub every interval. A
PR scout marks its interest (`interested`) and reads through `read`. Every unified watcher
starts the poller thread (`ensure_running`), and the one holding its lock reads all PRs
of recent interest each minute in one cheap query (pr_changes), re-reading in full only a
PR that changed or was last read `_REFRESH` ago (`_CHECKS_REFRESH` while checks run).

A snapshot file's mtime is when the poller last confirmed it current, and the heartbeat
file's mtime is when the poller's process last showed it still holds the lock; it beats on
its own timer, so slow GitHub reads can't make a live poller look dead. While it is recent, a
watched PR is read only from its snapshot: a poller that falls behind must not send every
scout to GitHub at once. A snapshot the live poller hasn't confirmed for `_BEHIND` counts
as a failed read, so its scouts report the outage. Only a dead poller sends scouts to
GitHub; the next watcher to try the lock takes over within a minute.
"""

import json
import os
import threading
import time
from concurrent import futures
from pathlib import Path

from ..log import get_logger
from . import cursors, github_api, pr_activity, pr_changes, waiter_lock

_INTERVAL = 60.0
_INTEREST = 300.0  # a scout polls at least this often while it watches
_REFRESH = 900.0
_CHECKS_REFRESH = 300.0  # the fingerprint sees only a PR's first 100 checks
_STALE = 3 * _INTERVAL
_BEHIND = 300.0  # a live poller that hasn't confirmed a PR this long is failing to read it
_FORGET = 86400.0  # interest files older than this are removed
_READERS = 4
_BEAT = _INTERVAL / 2

_log = get_logger("watch.pr_poller")
_start = threading.Lock()
_started = threading.Event()


def _snapshot_path(repo: str, number: int) -> Path:
    return github_api.state_dir() / "pr" / repo / f"{number}.json"


def _interest_root() -> Path:
    return github_api.state_dir() / "interest"


def _heartbeat_path() -> Path:
    return github_api.state_dir() / "pr-poller.alive"


def _age(path: Path, now: float) -> float:
    try:
        return now - path.stat().st_mtime
    except FileNotFoundError:
        return float("inf")


def _beat() -> None:
    _heartbeat_path().parent.mkdir(parents=True, exist_ok=True)
    _heartbeat_path().touch()


def interested(repo: str, number: int, watcher: str) -> None:
    path = _interest_root() / repo / str(number) / watcher
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def _saved(repo: str, number: int) -> dict | None:
    try:
        return json.loads(_snapshot_path(repo, number).read_text())["repository"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def snapshot(repo: str, number: int) -> dict | None:
    """The PR's `repository` as the poller last confirmed it; None when missing or stale."""
    if _age(_snapshot_path(repo, number), time.time()) > _STALE:
        return None

    return _saved(repo, number)


def _watched(repo: str, number: int, now: float) -> bool:
    return any(_age(p, now) < _INTEREST for p in (_interest_root() / repo / str(number)).glob("*"))


def read(repo: str, number: int) -> dict | None:
    """The PR as the poller has it, or a read from GitHub, saved as its snapshot, when the
    poller can't have it.

    That is when the PR has no snapshot yet, nobody watches it, or the poller is dead.
    None while GitHub reads are paused or the live poller is failing to read the PR,
    unless the snapshot is still current.
    """
    if (current := snapshot(repo, number)) is not None:
        return current

    if github_api.paused():
        return None

    now = time.time()
    path = _snapshot_path(repo, number)
    if _age(_heartbeat_path(), now) < _STALE and _watched(repo, number, now) and path.exists():
        return _saved(repo, number) if _age(path, now) < _BEHIND else None

    r = pr_activity.read(repo, number)
    if r is not None:  # so no snapshot is older than what a scout has seen; the poller re-reads it
        cursors.write_json(path, {"fingerprint": "", "fetched": now, "repository": r})
    return r


def _wanted(now: float) -> set[pr_changes.Key]:
    wanted = set()
    for path in _interest_root().glob("*/*/*/*"):
        age = _age(path, now)
        if age > _FORGET:
            path.unlink(missing_ok=True)
        elif age < _INTEREST and path.parent.name.isdigit():
            wanted.add((f"{path.parents[2].name}/{path.parents[1].name}", int(path.parent.name)))
    return wanted


def _current(path: Path, fingerprint: str, now: float) -> bool:
    """Whether the saved snapshot still stands: same fingerprint, and recent while the PR is open.

    The fingerprint carries the PR's state, so a merged or closed PR that reopens changes it.
    """
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        return False

    if saved.get("fingerprint") != fingerprint:
        return False

    repository = saved["repository"]
    if repository["pullRequest"]["state"] != "OPEN":
        return True

    running = any(c.outcome == "pending" for c in pr_activity.parse(repository, ()).checks)
    return now - float(saved.get("fetched", 0)) < (_CHECKS_REFRESH if running else _REFRESH)


def _refresh(key: pr_changes.Key, fingerprint: str, now: float) -> None:
    r = pr_activity.read(*key)
    if r is not None:
        cursors.write_json(
            _snapshot_path(*key), {"fingerprint": fingerprint, "fetched": now, "repository": r}
        )


def _cycle(now: float) -> None:
    """Confirm every unchanged snapshot first, so the full reads that follow make none stale."""
    _beat()
    due = []
    for key, fingerprint in pr_changes.fingerprints(_wanted(now)).items():
        path = _snapshot_path(*key)
        if _current(path, fingerprint, now):
            os.utime(path)
        else:
            due.append((key, fingerprint))

    with futures.ThreadPoolExecutor(_READERS) as pool:
        for done in futures.as_completed(pool.submit(_refresh, k, f, now) for k, f in due):
            done.result()


def _keep_beating(stop: threading.Event) -> None:
    """The heartbeat until `stop`; the poller never sets it, since it holds the lock until exit."""
    _beat()
    while not stop.wait(_BEAT):
        _beat()


def _run() -> None:
    lock_path = github_api.state_dir() / "pr-poller.lock"
    lock = None
    wait = _INTERVAL  # this watcher's scouts make the first reads themselves
    while True:
        time.sleep(wait)
        started = time.monotonic()
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            if not lock and (lock := waiter_lock.acquire(lock_path, grace=0)):
                threading.Thread(
                    target=_keep_beating,
                    args=(threading.Event(),),
                    name="pr-poller-beat",
                    daemon=True,
                ).start()
            if lock:
                _cycle(time.time())
        except Exception:  # the thread's top level: a dead poller would hold its lock
            _log.exception("PR poller cycle failed")
        wait = max(0.0, _INTERVAL - (time.monotonic() - started))


def ensure_running() -> None:
    with _start:
        if _started.is_set():
            return

        _started.set()
    threading.Thread(target=_run, name="pr-poller", daemon=True).start()
