"""Logs what the inbox's event loop was doing whenever it stops turning for a moment."""

import asyncio
import collections
import sys
import threading
import time
import traceback
import types

from ...log import get_logger

_log = get_logger("tui.loop")

_BEAT_SECONDS = 0.05
_KEPT_SECONDS = 60.0
_DUMP_SECONDS = 1.0
_BUSY_WINDOW_SECONDS = 5.0
_BUSY_SHARE = 0.5  # a window busier than this is logged with where the time went


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


def _waiting(frame: types.FrameType | None) -> bool:
    """Whether the loop thread is in its selector, waiting for something to do."""
    return frame is not None and frame.f_globals.get("__name__") == "selectors"


class Watchdog:
    """The loop stamps the time every `_BEAT_SECONDS` and records a late stamp as a stall.

    A thread reads the loop thread's stack while a stamp is overdue, since by the
    time the loop can record the stall it is no longer where it was blocked.
    """

    def __init__(self, threshold: float) -> None:
        self._threshold = threshold
        self._beat = time.monotonic()
        self._sampled = (0.0, "")  # the overdue beat, and where the loop was
        self._dumped = 0.0
        self._busy: collections.Counter[str] = collections.Counter()
        self._samples = 0
        self._window = time.monotonic()
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

    def _sample_busy(self, frame: types.FrameType | None) -> None:
        """Log a window in which the loop was mostly busy, though perhaps never long at once."""
        self._samples += 1
        if not _waiting(frame):
            self._busy[_where(frame)] += 1
        now = time.monotonic()
        if now - self._window < _BUSY_WINDOW_SECONDS:
            return

        busy = sum(self._busy.values())
        if busy > self._samples * _BUSY_SHARE:
            _log.warning(
                "loop busy %.0f%% over %.0f s, mostly in:\n%s",
                100 * busy / self._samples,
                now - self._window,
                "\n".join(
                    f"  {100 * n / self._samples:.0f}% {where}"
                    for where, n in self._busy.most_common(5)
                ),
            )
        self._busy.clear()
        self._samples = 0
        self._window = now

    def _watch(self, loop_thread: int) -> None:
        while not self._stopped.wait(_BEAT_SECONDS / 2):
            beat = self._beat
            late = time.monotonic() - beat - _BEAT_SECONDS
            if self._sampled[0] != beat and late >= self._threshold / 2:
                self._sampled = (beat, _where(sys._current_frames().get(loop_thread)))
            self._sample_busy(sys._current_frames().get(loop_thread))
            if self._dumped != beat and late >= _DUMP_SECONDS:
                self._dumped = beat
                _log.warning(
                    "loop blocked for %.1f s so far in:\n%s",
                    late,
                    "".join(traceback.format_stack(sys._current_frames().get(loop_thread))),
                )

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
