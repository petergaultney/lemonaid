"""How a watch loop sleeps between checks: on timers, or until a source it reads changes.

A loop given `TIMERS` checks every interval, as a one-shot `watch --self` does. The scout
host gives its scouts a kqueue hub (`kqueue_waits`), so an idle loop sleeps up to `idle`
seconds and wakes early when one of its files, directories or processes changes.
"""

import threading
import typing as ty
from collections import abc
from pathlib import Path

Unwatch = abc.Callable[[], None]


class Waits(ty.Protocol):
    idle: float | None  # the longest idle sleep; None keeps each loop's own interval

    def watch(
        self,
        paths: abc.Iterable[Path],
        pids: abc.Iterable[int],
        wake: threading.Event,
        contents: abc.Iterable[Path] = (),
    ) -> Unwatch:
        """Set *wake* whenever a path in *paths* or its directory changes, a pid exits, or a
        file in one of the *contents* directories changes."""
        ...

    def wake_all(self) -> None:
        """Wake every watching loop, so one that is stopping notices at once."""
        ...


class _Timers:
    idle = None

    def watch(
        self,
        paths: abc.Iterable[Path],
        pids: abc.Iterable[int],
        wake: threading.Event,
        contents: abc.Iterable[Path] = (),
    ) -> Unwatch:
        return lambda: None

    def wake_all(self) -> None:
        pass


TIMERS: Waits = _Timers()


def sleep_for(waits: Waits, interval: float, busy: bool) -> float:
    """How long a loop sleeps: its interval while busy or on timers, else the idle sleep."""
    return interval if busy or waits.idle is None else max(interval, waits.idle)
