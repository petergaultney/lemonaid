"""The OpenClaw turns running and failed, as the gateway's events say while a held connection
(`gateway.hold`) reads them. Failures go to `failures`.

A run sends `agent` events while it works and ends with a `lifecycle` event whose phase is
`end` or `error`; an `error` may be followed by a retry of the same run.
"""

import threading
import time
from collections import abc

from . import failures

_TERMINAL = frozenset({"end", "error"})
_RECORD_EVERY_MS = 60_000  # a running turn's record is renewed this often, so it never goes stale

_lock = threading.Lock()
_ended: dict[str, int] = {}  # session key: when its last turn ended, in ms
_recorded: dict[str, int] = {}  # session key: when its running turn was last recorded, in ms
_started: dict[str, int] = {}  # session key: when its running turn began, in ms

# A session key; its turn running as of a time in seconds, or None once it is over; and when that
# turn started and the session's last turn ended (0 for none yet).
Record = abc.Callable[[str, float | None, float, float], None]


def note(payload: dict) -> None:
    """Keep a failed turn from an `agent` event's payload; anything else is no failure."""
    data = payload.get("data") or {}
    key, run = str(payload.get("sessionKey") or ""), str(payload.get("runId") or "")
    if payload.get("stream") != "lifecycle" or data.get("phase") != "error" or not key:
        return

    failures.record(key, run, int(payload.get("ts") or 0), str(data.get("error") or ""))


def track(payload: dict, record: Record) -> None:
    """*record* a session's turn as running as of an `agent` event's time, or as over at its
    end. An event older than the turn's end is a straggler from that turn."""
    data, key = payload.get("data") or {}, str(payload.get("sessionKey") or "")
    if not key:
        return

    at = int(payload.get("ts") or time.time() * 1000)
    ended = payload.get("stream") == "lifecycle" and data.get("phase") in _TERMINAL
    with _lock:
        last = _ended.get(key, -1)
        if at < last or (at == last and not ended):
            return

        started = _started.setdefault(key, at)
        if ended:
            _ended[key] = at
            _recorded.pop(key, None)
            _started.pop(key, None)
        else:
            if at - _recorded.get(key, -_RECORD_EVERY_MS) < _RECORD_EVERY_MS:
                return

            _recorded[key] = at
    record(
        key, None if ended else at / 1000, started / 1000, (at if ended else max(last, 0)) / 1000
    )
