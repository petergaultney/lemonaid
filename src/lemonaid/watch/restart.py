"""Restarting running `watch --self` waiters into the installed lemonaid, by signal.

A push scout lives as long as its Claude session, and any waiter can sit for hours,
so either can outlast a reinstall and keep reading briefs with the old code. Each
`watch --self` waiter records its lemonaid version in the registry and restarts
itself, once nothing it has detected is waiting to be delivered, when it gets
`SIGNAL`. `lemonaid watch restart` sends it to chosen waiters, and the first
lemonaid command of a new version sends it to every waiter from the same install
whose loaded lemonaid modules changed.
"""

import contextlib
import fcntl
import hashlib
import importlib.metadata
import os
import pathlib
import signal
import sys
import threading
from collections import abc

from ..log import get_logger
from . import registry

_log = get_logger("watch.restart")
_PACKAGE = pathlib.Path(__file__).resolve().parent.parent

SIGNAL = signal.SIGUSR1
_requested = False


def version() -> str:
    """The installed lemonaid's version; a dev build's includes its commit."""
    try:
        return importlib.metadata.version("lemonaid-inbox")
    except importlib.metadata.PackageNotFoundError:
        return ""


def _note(signum: int, frame: object) -> None:
    """A second SIGNAL can run this inside the first, so a lock here (say a
    `threading.Event`) would deadlock the main thread for good."""
    global _requested
    _requested = True


@contextlib.contextmanager
def listening() -> abc.Iterator[None]:
    """Note a restart request from `SIGNAL` until the block exits; main thread only.

    After a request, `SIGNAL` stays ignored, and an ignored signal stays ignored
    across `exec`, so a second request can't kill the process while it restarts.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    global _requested
    _requested = False
    previous = signal.signal(SIGNAL, _note)
    try:
        yield
    finally:
        signal.signal(SIGNAL, signal.SIG_IGN if _requested else previous)


def requested() -> bool:
    return _requested


def restart() -> None:
    """Replace this process with the installed lemonaid, run with the same arguments."""
    print("Restarting this watcher with the installed lemonaid", file=sys.stderr, flush=True)
    os.execv(sys.executable, [sys.executable, "-m", "lemonaid", *sys.argv[1:]])


def send(waiters: abc.Iterable[registry.Waiter]) -> list[registry.Waiter]:
    """Ask each restartable waiter in *waiters* that still runs to restart; the ones asked."""
    sent = []
    for waiter in waiters:
        if not waiter.restartable or not registry.current(waiter):
            continue

        try:
            os.kill(waiter.pid, SIGNAL)
        except ProcessLookupError:
            continue

        sent.append(waiter)
    return sent


def _digest(paths: abc.Iterable[str]) -> str:
    """Of the installed source at *paths*, relative to the lemonaid package."""
    h = hashlib.sha256()
    for rel in paths:
        try:
            source = (_PACKAGE / rel).read_bytes()
        except OSError:
            source = b""
        h.update(f"{rel}\0{len(source)}\0".encode() + source)
    return h.hexdigest()


def fingerprint() -> tuple[str, tuple[str, ...]]:
    """The digest and paths of the lemonaid modules this process has loaded."""
    paths = set()
    for module in list(sys.modules.values()):
        try:
            paths.add(str(pathlib.Path(module.__file__).resolve().relative_to(_PACKAGE)))
        except (AttributeError, TypeError, ValueError):
            continue
    ordered = tuple(sorted(paths))
    return _digest(ordered), ordered


def _outdated(waiter: registry.Waiter, current: str) -> bool:
    """Whether *waiter* runs from this install and loaded code that has since changed.

    One that records no prefix or code predates these fields and is always asked.
    """
    if waiter.version == current or waiter.prefix not in ("", sys.prefix):
        return False

    return not waiter.code or waiter.code != _digest(waiter.code_paths)


def _seen_path() -> pathlib.Path:
    """One per install, so a dev checkout and the installed tool don't take turns rewriting it."""
    return registry.root() / "versions" / hashlib.sha256(sys.prefix.encode()).hexdigest()[:16]


def _seen(path: pathlib.Path, current: str) -> bool:
    try:
        return path.read_text() == current
    except FileNotFoundError:
        return False


def after_upgrade() -> list[registry.Waiter]:
    """Once per installed version: ask every outdated waiter of this install to restart.

    Every lemonaid command calls this, so it costs one small file read when nothing
    changed. Commands that start together after an install take turns on a lock, so
    only the first one sends.
    """
    current = version()
    path = _seen_path()
    if not current or _seen(path, current):
        return []

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path.with_suffix(".lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if _seen(path, current):
                return []

            path.write_text(current)
            sent = send(w for w in registry.running() if _outdated(w, current))
    except OSError as error:
        _log.warning("could not record lemonaid %s: %s", current, error)
        return []

    if sent:
        _log.info("lemonaid %s asked %d waiters to restart", current, len(sent))
    return sent
