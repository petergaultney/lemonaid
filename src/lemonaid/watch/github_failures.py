"""What a scout does after a failed GitHub read: wait out a shared pause, or back off.

A lemon hears about an outage once, covering all its GitHub subscriptions, and only once
reads have failed for the debounce period with none succeeding; a read that succeeds ends
the outage, so a short one wakes nobody. A rate-limit pause counts as an outage. A lemon's
scouts run in parallel, so one claims the notice under a lock and delivers it after releasing
the lock: a scout waiting on that lock could not finish the poll that lets the batch, and so
that delivery, go out. Every failure backs off, doubling from the subscription's interval up
to `_MAX_DELAY` with jitter, or waits out the pause.
"""

import json
import random
import time
import uuid
from collections import abc
from pathlib import Path

from . import cursors, delivery, failure_state, github_api

_MAX_DELAY = 600.0
_CLAIM = 600.0  # a claim older than this is from a scout that died delivering


def _retry_delay(attempts: int, interval: float) -> float:
    ceiling = min(_MAX_DELAY, interval * 2 ** min(attempts, 20))
    return random.uniform(ceiling / 2, ceiling)


def _outage_path(root: Path) -> Path:
    return root / "failures" / "github-outage.json"


def _pause_message(pause: github_api.Pause) -> str:
    until = time.strftime("%H:%M", time.localtime(pause.until))
    if pause.reason == "secondary":
        return f"GitHub's secondary rate limit paused GitHub watches until {until}; they resume on their own"

    return f"The GitHub API quota is used up until {until}; GitHub watches resume on their own then"


def _down_message(since: float, label: str) -> str:
    return (
        f"Cannot reach GitHub for {label} and your other GitHub watches since"
        f" {time.strftime('%H:%M', time.localtime(since))}; they keep retrying and say nothing more"
        " until a read succeeds"
    )


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _claim(path: Path, now: float, debounce: float) -> tuple[dict, bool]:
    """The lemon's outage, started now if none was, and whether this scout is the one to
    report it, which it then owns."""
    with github_api.locked(path.with_suffix(".lock")):
        saved = _load(path) or {"id": uuid.uuid4().hex, "since": now}
        due = (
            not saved.get("delivered")
            and now - float(saved["since"]) >= debounce
            and now - float(saved.get("claimed", 0)) >= _CLAIM
        )
        saved = {**saved, **({"claimed": now} if due else {})}
        cursors.write_json(path, saved)
    return saved, due


def _amend(path: Path, outage: str, change: abc.Callable[[dict], dict]) -> None:
    """Change the record of *outage*, unless a read succeeded and ended it meanwhile."""
    with github_api.locked(path.with_suffix(".lock")):
        saved = _load(path)
        if saved.get("id") == outage:
            cursors.write_json(path, change(saved))


def _tell(path: Path, outage: str, message: str, deliver: abc.Callable[[str], object]) -> None:
    try:
        deliver(message)
    except delivery.Failed:
        _amend(path, outage, lambda saved: {k: v for k, v in saved.items() if k != "claimed"})
        raise
    _amend(path, outage, lambda saved: {**saved, "delivered": True})


def failed(
    root: Path,
    failure: Path,
    label: str,
    deliver: abc.Callable[[str], object],
    interval: float,
    debounce: float,
) -> float:
    """Seconds to wait before the next read. `failure` counts this subscription's failures.

    A wait never runs past the outage's report deadline, so a long pause is still reported;
    a read during a pause returns at once without calling GitHub.
    """
    now, pause = time.time(), github_api.paused()
    attempts = failure_state.count(failure)
    path = _outage_path(root)
    outage, due = _claim(path, now, debounce)
    if due:
        message = _pause_message(pause) if pause else _down_message(outage["since"], label)
        _tell(path, outage["id"], message, deliver)
    wait = max(interval, pause.until - now) if pause else _retry_delay(attempts, interval)
    deadline = float(outage["since"]) + debounce - now
    return min(wait, deadline) if not outage.get("delivered") and deadline > 0 else wait


def recovered(root: Path, failure: Path) -> None:
    failure_state.clear(failure)
    if not github_api.paused():  # a read begun before the pause can still succeed
        path = _outage_path(root)
        with github_api.locked(path.with_suffix(".lock")):
            failure_state.clear(path)
