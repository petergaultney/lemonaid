"""Logs what the inbox's event loop was doing whenever it stops turning for a moment."""

import asyncio
import collections
import sys
import threading
import time
import types

from ...log import get_logger

_log = get_logger("tui.loop")

_BEAT_SECONDS = 0.05
_KEPT_SECONDS = 60.0


def _name(frame: types.FrameType) -> str:
    return f"{frame.f_globals.get('__name__', '?')}.{frame.f_code.co_qualname}".removeprefix(
        "lemonaid."
    )


def _where(frame: types.FrameType | None) -> str:
    """The innermost lemonaid call, two of its lemonaid callers and the call it made."""
    frames = []
    while frame is not None:
        frames.append(frame)
        frame = frame.f_back
    ours = [
        i for i, f in enumerate(frames) if f.f_globals.get("__name__", "").startswith("lemonaid.")
    ]
    if not ours:
        return " -> ".join(_name(f) for f in reversed(frames[:3])) or "?"

    inner = ours[0]
    chosen = ours[:3] + ([inner - 1] if inner else [])
    return " -> ".join(_name(frames[i]) for i in sorted(chosen, reverse=True))


class Watchdog:
    """The loop stamps the time every `_BEAT_SECONDS` and records a late stamp as a stall.

    A thread reads the loop thread's stack while a stamp is overdue, since by the
    time the loop can record the stall it is no longer where it was blocked.
    """

    def __init__(self, threshold: float) -> None:
        self._threshold = threshold
        self._beat = time.monotonic()
        self._sampled = (0.0, "")  # the overdue beat, and where the loop was
        self._stalls: collections.deque[tuple[float, float]] = collections.deque()
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._timer: asyncio.TimerHandle | None = None

    def _record(self, at: float, seconds: float, where: str) -> None:
        _log.warning("loop blocked %.0f ms in %s", seconds * 1000, where)
        with self._lock:
            self._stalls.append((at, seconds))
            while self._stalls[0][0] < at - _KEPT_SECONDS:
                self._stalls.popleft()

    def _stamp(self, loop: asyncio.AbstractEventLoop) -> None:
        now = time.monotonic()
        late = now - self._beat - _BEAT_SECONDS
        if late >= self._threshold:
            beat, where = self._sampled
            self._record(now, late, where if beat == self._beat else "an unsampled call")
        self._beat = now
        self._timer = loop.call_later(_BEAT_SECONDS, self._stamp, loop)

    def _watch(self, loop_thread: int) -> None:
        while not self._stopped.wait(_BEAT_SECONDS / 2):
            beat = self._beat
            if self._sampled[0] != beat and time.monotonic() - beat - _BEAT_SECONDS >= (
                self._threshold / 2
            ):
                self._sampled = (beat, _where(sys._current_frames().get(loop_thread)))

    def start(self) -> None:
        """Call on the loop's own thread, which is the one watched."""
        loop = asyncio.get_running_loop()
        self._beat = time.monotonic()
        self._timer = loop.call_later(_BEAT_SECONDS, self._stamp, loop)
        threading.Thread(
            target=self._watch, args=(threading.get_ident(),), daemon=True, name="loop-watchdog"
        ).start()

    def stop(self) -> None:
        self._stopped.set()
        if self._timer is not None:
            self._timer.cancel()

    def worst(self, now: float) -> float:
        """The longest stall, in seconds, of those that ended in the last minute."""
        with self._lock:
            while self._stalls and self._stalls[0][0] < now - _KEPT_SECONDS:
                self._stalls.popleft()
            return max((seconds for _, seconds in self._stalls), default=0.0)
