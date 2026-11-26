"""The OpenClaw turns that failed, as the gateway's events say while a held connection
(`gateway.hold`) reads them. The gateway keeps no record of a turn that failed before its
lemon wrote anything, so its conversation alone would show the lemon saying nothing.
"""

import threading
import typing as ty

_KEPT = 5  # failed turns kept for each session

_lock = threading.Lock()
_failed: dict[str, dict[str, "Failure"]] = {}  # session key: by run id, oldest first


class Failure(ty.NamedTuple):
    at_ms: int
    why: str


def note(payload: dict) -> None:
    """Keep a failed turn from an `agent` event's payload; anything else is no failure."""
    data = payload.get("data") or {}
    key, run = str(payload.get("sessionKey") or ""), str(payload.get("runId") or "")
    if payload.get("stream") != "lifecycle" or data.get("phase") != "error" or not key:
        return

    with _lock:
        runs = _failed.setdefault(key, {})
        runs.setdefault(run, Failure(int(payload.get("ts") or 0), str(data.get("error") or "")))
        for old in list(runs)[:-_KEPT]:
            del runs[old]


def failed(session_key: str) -> list[Failure]:
    """The session's failed turns seen since this process started, oldest first."""
    with _lock:
        return list(_failed.get(session_key, {}).values())
