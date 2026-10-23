"""Restarting running `watch --self` waiters into the installed lemonaid, by signal.

A push scout lives as long as its Claude session, and any waiter can sit for hours,
so either can outlast a reinstall and keep reading briefs with the old code. Each
`watch --self` waiter records its lemonaid version in the registry and restarts
itself, once nothing it has detected is waiting to be delivered, when it gets
`SIGNAL`. `lemonaid watch restart` sends it to chosen waiters, and the first
lemonaid command of a new version sends it to every waiter of an older one.
"""

import contextlib
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


def _seen_path() -> pathlib.Path:
    return registry.root() / "version"


def after_upgrade() -> list[registry.Waiter]:
    """Once per installed version: ask every waiter started by another version to restart.

    Every lemonaid command calls this, so it costs one small file read when nothing
    changed.
    """
    current = version()
    path = _seen_path()
    try:
        if not current or path.read_text() == current:
            return []
    except FileNotFoundError:
        pass

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(current)
    except OSError as error:
        _log.warning("could not record lemonaid %s: %s", current, error)
        return []

    sent = send(w for w in registry.running() if w.version != current)
    if sent:
        _log.info("lemonaid %s asked %d waiters to restart", current, len(sent))
    return sent
