"""Logs what the inbox is stuck on while it ignores keys and the mouse.

Keys and mouse events reach the inbox through the app's message queue, which
handles one message at a time. A handler that awaits something that never
finishes leaves the queue stuck while the event loop, timers and painting carry
on, so the loop watchdog sees nothing. An unclosed `batch_update` instead stops
all painting. Both are logged here, with every busy task's await chain, while
they are still happening.
"""

import asyncio
import threading
import time
import types
import typing as ty

from textual.app import App
from textual.message_pump import MessagePump

from ...log import get_logger

_log = get_logger("tui.input")

_PROBE_SECONDS = 0.5


def _frames(coro: object) -> list[types.FrameType]:
    """The frames *coro* is suspended in, outermost first, following what each awaits."""
    frames = []
    while coro is not None:
        frame = getattr(coro, "cr_frame", None) or getattr(coro, "gi_frame", None)
        if frame is None:
            break
        frames.append(frame)
        coro = getattr(coro, "cr_await", None) or getattr(coro, "gi_yieldfrom", None)
    return frames


def _chain(task: asyncio.Task) -> list[str]:
    return [
        f"{f.f_code.co_filename}:{f.f_lineno} {f.f_code.co_qualname}"
        for f in _frames(task.get_coro())
    ]


def _idle(chain: list[str]) -> bool:
    """A message pump waiting for its next message, or a timer waiting for its tick
    rather than running its callback.
    """
    return any(line.endswith("._get_message") for line in chain) or (
        any(line.endswith("Timer._run") for line in chain)
        and not any(line.endswith("Timer._tick") for line in chain)
    )


def busy_tasks() -> str:
    """Every task on the running loop that is not just waiting for work, with its await chain."""
    return "\n".join(
        f"  task {task.get_name()}:\n" + "\n".join(f"    {line}" for line in chain)
        for task in asyncio.all_tasks()
        if (chain := _chain(task)) and not _idle(chain)
    )


class Watchdog:
    """Sends a message every `_PROBE_SECONDS` to the app, its screen and the focused
    widget, the queues a key passes through, and notices when one goes unanswered.

    A thread does the noticing, since a stuck queue cannot report itself; it asks
    the loop for the task dump, which works because the loop is free.
    """

    def __init__(self, app: App[ty.Any], threshold: float) -> None:
        self._app = app
        self._threshold = threshold
        self._sent: dict[MessagePump, float] = {}
        self._overdue: set[MessagePump] = set()
        self._ticked = time.monotonic()  # the loop watchdog covers a loop that stops ticking
        self._batched_since: float | None = None
        self._reported = False
        self._stopped = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    def _answered(self, pump: MessagePump) -> None:
        sent = self._sent.pop(pump, None)
        if pump in self._overdue and sent is not None:
            self._overdue.discard(pump)
            _log.warning("%r answered again after %.1f s", pump, time.monotonic() - sent)

    def _probe(self) -> None:
        self._ticked = time.monotonic()
        self._sent = {p: t for p, t in self._sent.items() if not (p._closing or p._closed)}
        for pump in dict.fromkeys(p for p in (self._app, self._app.screen, self._app.focused) if p):
            if pump not in self._sent:
                self._sent[pump] = self._ticked
                pump.call_later(self._answered, pump)

    def _dump(self, what: str) -> None:
        _log.warning(
            "%s; batches open: %d; busy tasks:\n%s",
            what,
            self._app._batch_count,
            busy_tasks() or "  (none)",
        )

    def _check(self, now: float) -> str:
        """What is stuck, or empty when nothing is."""
        if now - self._ticked >= self._threshold:
            return ""

        if stuck := [
            (pump, now - sent)
            for pump, sent in list(self._sent.items())
            if now - sent >= self._threshold
        ]:
            self._overdue.update(pump for pump, _ in stuck)
            return "; ".join(
                f"{pump!r} has not handled a message for {age:.1f} s" for pump, age in stuck
            )

        batched = self._app._batch_count
        if not batched:
            self._batched_since = None
        elif self._batched_since is None:
            self._batched_since = now
        elif now - self._batched_since >= self._threshold:
            return (
                f"painting held by {batched} open batch(es) for {now - self._batched_since:.1f} s"
            )

        return ""

    def _watch(self) -> None:
        while not self._stopped.wait(_PROBE_SECONDS / 2):
            stuck = self._check(time.monotonic())
            if stuck and not self._reported and self._loop is not None:
                self._reported = True
                self._loop.call_soon_threadsafe(self._dump, stuck)
            elif not stuck:
                self._reported = False

    def start(self) -> None:
        """Call on the loop's own thread, once the app is running."""
        self._loop = asyncio.get_running_loop()
        self._app.set_interval(_PROBE_SECONDS, self._probe)
        threading.Thread(target=self._watch, daemon=True, name="input-watchdog").start()

    def stop(self) -> None:
        self._stopped.set()
