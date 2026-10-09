"""Stopping a registered waiter, leaving a note that says who asked."""

import os
import signal
import time

from ..log import get_logger
from . import registry, stop_sender, waiter_lock

_log = get_logger("watch.stopping")


def _wait_for_exit(waiter: registry.Waiter, grace: float) -> None:
    deadline = time.monotonic() + grace
    while waiter_lock.held(registry.entry(waiter.pid)):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"{waiter.kind} waiter pid {waiter.pid} did not exit")

        time.sleep(0.05)


def stop(waiter: registry.Waiter, by: str, grace: float = 2.0) -> None:
    """SIGTERMs `waiter` for the lemon `by` if it still holds its entry, then waits up to `grace` seconds for it.

    The note naming `by` exists only while the stop is in flight, so a later
    signal from elsewhere is never blamed on this one.
    """
    path = registry.entry(waiter.pid)
    if not waiter_lock.held(path):
        return

    stop_sender.record(path, by)
    _log.info("%s stops %s waiter pid %s of %s", by, waiter.kind, waiter.pid, waiter.channel)
    try:
        os.kill(waiter.pid, signal.SIGTERM)
        _wait_for_exit(waiter, grace)
    except ProcessLookupError:
        return
    finally:
        stop_sender.clear(path)
