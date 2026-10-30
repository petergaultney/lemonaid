"""Whether anything an inbox refresh reads may have changed since the last one loaded.

Most refreshes find nothing changed. The database's `data_version`, read on a connection
kept open, changes with each commit by any other connection, and a kqueue hub watches the
briefs and the lemons' inboxes. Liveness and relative times change with no event, so a
load is also due every `FULL_SECONDS`.
"""

import sqlite3
import threading
import typing as ty
from collections import abc
from pathlib import Path

from ....watch import kqueue_waits, waits

FULL_SECONDS = 5.0  # as often as an unchanged frame was redrawn for its ages


def hub() -> waits.Waits | None:
    """The kqueue hub to watch with, or None where there is no kqueue and every tick loads."""
    if not kqueue_waits.available():
        return None

    kqueue_waits.raise_file_limit()
    return kqueue_waits.Hub()


class Changes:
    """`due` runs on one refresh worker at a time; `mark` and `close` on any thread."""

    def __init__(self, db_path: Path, watched: abc.Iterable[Path], hub: waits.Waits | None) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False) if hub else None
        self._using = threading.Lock()  # so `close` never closes it under a worker's read
        self._version: int | None = None
        self._woken = threading.Event()
        self._unwatch = hub.watch((), (), self._woken, contents=watched) if hub else None
        self._loaded: tuple[ty.Hashable, float] | None = None  # the request and when

    def mark(self) -> None:
        """Something a load reads arrived from a worker of the inbox's own."""
        self._woken.set()

    def due(self, request: ty.Hashable, now: float) -> bool:
        """Whether to load *request* now; a load it allows counts as done."""
        if self._conn is None:
            return True

        with self._using:
            try:
                version = self._conn.execute("PRAGMA data_version").fetchone()[0]
            except sqlite3.Error:  # closed as the inbox stops, or the database is locked
                version = None
        if (
            self._loaded is not None
            and self._loaded[0] == request
            and now - self._loaded[1] < FULL_SECONDS
            and version is not None
            and version == self._version
            and not self._woken.is_set()
        ):
            return False

        self._woken.clear()
        self._version = version
        self._loaded = (request, now)
        return True

    def close(self) -> None:
        if self._unwatch is not None:
            self._unwatch()
        with self._using:
            if self._conn is not None:
                self._conn.close()
