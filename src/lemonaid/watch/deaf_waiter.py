"""Stopping a lemon's unified waiter that holds its lock but no longer polls.

Such a waiter delivers nothing, yet its lock keeps a replacement from starting, so
whatever starts a scout clears it first. Its undelivered changes stay on disk for the
next waiter, as after `lemonaid watch stop`.
"""

import contextlib
import os
import signal

from ..log import get_logger
from . import registry, stopping, wait_state

_log = get_logger("watch.deaf_waiter")


def clear(lemon_id: str, by: str) -> None:
    if not wait_state.deaf(lemon_id):
        return

    for waiter in registry.running_for("wait", lemon_id):
        _log.warning(
            "stopping deaf waiter pid %s of %s: no poll for %.0fs",
            waiter.pid,
            lemon_id,
            wait_state.silent_for(lemon_id),
        )
        try:
            stopping.stop(waiter, by)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                os.kill(waiter.pid, signal.SIGKILL)
