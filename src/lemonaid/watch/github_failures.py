"""What a scout does after a failed GitHub read: wait out a shared pause, or back off.

A pause (see github_api) is told to each lemon once, since every watch on the machine
waits for the same reset. Its scouts run in parallel, so one claims the notice under a lock
and delivers it after releasing the lock: a scout waiting on that lock could not finish the
poll that lets the batch, and so that delivery, go out. Any other failure backs off, doubling from the subscription's
interval up to `_MAX_DELAY` with jitter, and is reported after three in a row.
"""

import json
import random
import time
from collections import abc
from pathlib import Path

from . import cursors, delivery, failure_state, github_api

_MAX_DELAY = 600.0
_CLAIM = 600.0  # a claim older than this is from a scout that died delivering


def _retry_delay(attempts: int, interval: float) -> float:
    ceiling = min(_MAX_DELAY, interval * 2 ** min(attempts, 20))
    return random.uniform(ceiling / 2, ceiling)


def _pause_path(root: Path) -> Path:
    return root / "failures" / "github-pause.json"


def _pause_message(pause: github_api.Pause) -> str:
    until = time.strftime("%H:%M", time.localtime(pause.until))
    if pause.reason == "secondary":
        return f"GitHub's secondary rate limit paused GitHub watches until {until}; they resume on their own"

    return f"The GitHub API quota is used up until {until}; GitHub watches resume on their own then"


def _claim(path: Path, message: str) -> bool:
    """Whether this scout is the one to deliver `message`, which it then owns."""
    with github_api.locked(path.with_suffix(".lock")):
        try:
            saved = json.loads(path.read_text())
        except (OSError, ValueError):
            saved = {}
        if saved.get("message") == message and (
            saved.get("delivered") or time.time() - float(saved.get("claimed", 0)) < _CLAIM
        ):
            return False

        cursors.write_json(path, {"message": message, "claimed": time.time()})
    return True


def _tell(path: Path, message: str, deliver: abc.Callable[[str], object]) -> None:
    if not _claim(path, message):
        return

    try:
        deliver(message)
    except delivery.Failed:
        failure_state.clear(path)  # unclaimed, so the next scout tries again
        raise
    cursors.write_json(path, {"message": message, "delivered": True})


def failed(
    root: Path, failure: Path, label: str, deliver: abc.Callable[[str], object], interval: float
) -> float:
    """Seconds to wait before the next read. `failure` counts this subscription's failures."""
    if pause := github_api.paused():
        _tell(_pause_path(root), _pause_message(pause), deliver)
        return max(interval, pause.until - time.time())

    attempts = failure_state.report(
        failure, f"Cannot reach GitHub for {label} after repeated attempts", deliver, threshold=3
    )
    return _retry_delay(attempts, interval)


def recovered(root: Path, failure: Path) -> None:
    failure_state.clear(failure)
    if not github_api.paused():  # a read begun before the pause can still succeed
        failure_state.clear(_pause_path(root))
