"""The inbox's periodic refresh: read on a worker thread, drawn on the UI thread.

A tick reads the database, briefs, `ps` and tmux, and any of them can stall: a
database another process is writing waits on its lock. On a worker the stall
delays the next redraw instead of the keys and mouse.
"""

import functools
import typing as ty
from collections import abc

from textual.app import App

from ....log import get_logger

_log = get_logger("tui")

_R = ty.TypeVar("_R")


class Ticks:
    """One load at a time; a tick that comes while one is loading is skipped,
    since the next tick after it reads fresher state anyway.
    """

    def __init__(self, app: App[ty.Any]) -> None:
        self._app = app
        self.busy = False

    def _finish(self, done: abc.Callable[[_R], None], result: _R) -> None:
        self.busy = False
        done(result)

    def _work(self, load: abc.Callable[[], _R], done: abc.Callable[[_R], None]) -> None:
        try:
            result = load()
        except Exception:  # the thread's top level; the next tick tries again
            _log.exception("inbox refresh could not load")
            self.busy = False
            return

        try:
            self._app.call_from_thread(self._app.call_later, self._finish, done, result)
        except RuntimeError:  # the app closed while this tick was loading
            self.busy = False

    def run(self, load: abc.Callable[[], _R], done: abc.Callable[[_R], None]) -> None:
        """Call *load* on a worker, then *done* with its result on the UI thread."""
        if self.busy:
            return

        self.busy = True
        self._app.run_worker(
            functools.partial(self._work, load, done),
            thread=True,
            group="refresh-tick",
            exit_on_error=False,
        )
