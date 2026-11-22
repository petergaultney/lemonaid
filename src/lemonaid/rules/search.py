"""Regex searches with a time limit, which Python's `re` doesn't have.

A SIGALRM timer interrupts a search, because `re` checks for signals while it backtracks.
Signals reach only the main thread, where the Stop hook and `lemonaid rules` run.
"""

import contextlib
import re
import signal
import typing as ty
from collections import abc


class TooSlow(Exception):
    pass


def _expire(signum: int, frame: ty.Any) -> None:
    raise TooSlow


@contextlib.contextmanager
def _limit(seconds: float) -> abc.Iterator[None]:
    previous = signal.signal(signal.SIGALRM, _expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def search(regex: str, text: str, seconds: float) -> re.Match[str] | None:
    """Raises TooSlow when compiling and searching take longer than *seconds*."""
    if seconds <= 0:
        raise TooSlow

    with _limit(seconds):
        return re.search(regex, text)
