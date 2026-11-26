"""Telling each open page when the grove changes, over a stream of server-sent events.

The grove window has Python push the grove to its page. In a browser, a page keeps a
`GET /api/changes` response open, and the server writes a line to it whenever a reload changed
what the page draws, so the page asks for the grove at once and otherwise not at all.

A browser holds at most six connections to one server, and each stream keeps one. So a client
gets at most *STREAMS_PER_CLIENT* streams, leaving the rest for the page's calls, and a page that
is turned away asks every few seconds instead.
"""

import collections
import contextlib
import json
import threading
import time
from collections import abc

STREAMS_PER_CLIENT = 2
HEARTBEAT_SECONDS = 15.0  # a comment this often, for anything between that drops quiet connections
CHECK_SECONDS = 1.0  # how often a stream checks that its page is still there


class Changes:
    """How many times the grove as the page draws it has changed, for the streams to wait on,
    and how many streams each client has open."""

    def __init__(self) -> None:
        self._changed = threading.Condition()
        self._count = 0
        self._last = ""
        self._open: collections.Counter[str] = collections.Counter()

    def saw(self, shown: object) -> None:
        """Count a change if *shown*, the grove as the page draws it, differs from the last."""
        text = json.dumps(shown, sort_keys=True, default=str)
        with self._changed:
            if text != self._last:
                self._last, self._count = text, self._count + 1
                self._changed.notify_all()

    def after(self, count: int, timeout: float) -> int:
        """The count once it differs from *count*, or as it is after *timeout* seconds."""
        with self._changed:
            self._changed.wait_for(lambda: self._count != count, timeout)
            return self._count

    @contextlib.contextmanager
    def admitted(self, client: str) -> abc.Iterator[bool]:
        """Whether *client* may open another stream, held open while it does."""
        with self._changed:
            ok = self._open[client] < STREAMS_PER_CLIENT
            if ok:
                self._open[client] += 1
        try:
            yield ok
        finally:
            if ok:
                with self._changed:
                    self._open[client] -= 1


def stream(
    changes: Changes,
    write: abc.Callable[[bytes], None],
    gone: abc.Callable[[], bool],
    heartbeat: float = HEARTBEAT_SECONDS,
    check: float = CHECK_SECONDS,
) -> None:
    """Write an event for each change until the page is *gone*, or *write* raises because it is."""
    count, quiet = changes.after(-1, 0), 0.0
    write(b"retry: 1000\n\n")  # how soon a page reconnects when the server restarts
    while not gone():
        now = changes.after(count, check)
        if now != count:
            write(f"data: {now}\n\n".encode())
            count, quiet = now, 0.0
        elif (quiet := quiet + check) >= heartbeat:
            write(b": still here\n\n")
            quiet = 0.0


def watch(
    mark: abc.Callable[[], str],
    write: abc.Callable[[bytes], None],
    gone: abc.Callable[[], bool],
    heartbeat: float = HEARTBEAT_SECONDS,
    check: float = CHECK_SECONDS,
) -> None:
    """Write an event each time *mark* changes, looking every *check* seconds, until the page is
    *gone*: for what the server only learns by asking, such as a lemon's conversation."""
    last, count, quiet = mark(), 0, 0.0
    write(b"retry: 1000\n\n")
    while not gone():
        time.sleep(check)
        now = mark()
        if now != last:
            last, count, quiet = now, count + 1, 0.0
            write(f"data: {count}\n\n".encode())
        elif (quiet := quiet + check) >= heartbeat:
            write(b": still here\n\n")
            quiet = 0.0
