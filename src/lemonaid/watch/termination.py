"""Telling a waiter's lemon why its waiter ended when SIGTERM stops it."""

import contextlib
import logging
import os
import pathlib
import signal
import sys
import threading
from collections import abc

from ..log import get_logger
from . import stop_sender

_log = get_logger("watch.registry")


def stopped_message(kind: str, targets: abc.Iterable[str], command: str, sender: str) -> str:
    return (
        f"This {kind} waiter ({', '.join(targets)}) was stopped by SIGTERM "
        f"from {sender}. If you didn't stop it yourself, rearm it with `{command}`."
    )


@contextlib.contextmanager
def reported(message: abc.Callable[[], str], entry: pathlib.Path) -> abc.Iterator[None]:
    """Logs and prints `message()` to stderr, and exits 143, if SIGTERM arrives.

    A harness reports a killed background task only by its exit code, so without
    this a lemon whose waiter another process killed cannot tell why it woke.
    *entry* is the waiter's registry entry, beside which `watch stop` leaves its note.
    Signal handlers belong to the main thread; elsewhere this does nothing.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def _exit(signum: int, _frame: object) -> None:
        try:
            text = message()
            level = logging.INFO if stop_sender.requested(entry) else logging.WARNING
            _log.log(level, "pid %s: %s", os.getpid(), text)
            print(text, file=sys.stderr, flush=True)
        finally:
            raise SystemExit(128 + signum)  # whatever reporting did

    previous = signal.signal(signal.SIGTERM, _exit)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)
