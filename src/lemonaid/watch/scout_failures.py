"""Push scouts that keep failing: per lemon, the last reason and how many attempts in a row failed.

The scout host waits longer before each retry as the count grows, and `watch --self
--status` and a recipient's deaf detail name the reason, so a scout restarted every few
seconds does not look like one that runs. A delivery, or a scout that stays up for
`SETTLED_SECONDS`, clears the record.
"""

import datetime as dt
import json
import os
import time
import typing as ty
from pathlib import Path

from ..log import get_logger

_log = get_logger("watch.scout_failures")

FAILING_AFTER = 2  # attempts in a row before a scout counts as failing
SETTLED_SECONDS = 120.0
_MAX_DELAY = 600.0


class Failure(ty.NamedTuple):
    reason: str
    count: int
    since: float  # epoch seconds of the first failure in the run


def _path(lemon_id: str) -> Path:
    state = Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid").expanduser()
    return state / "scout-failures" / f"{lemon_id}.json"


def read(lemon_id: str) -> Failure | None:
    try:
        return Failure(**json.loads(_path(lemon_id).read_text()))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError) as error:
        _log.warning("unreadable scout failure record for %s: %s", lemon_id, error)
        return None


def record(lemon_id: str, reason: str) -> Failure:
    previous = read(lemon_id)
    failure = Failure(
        reason,
        previous.count + 1 if previous else 1,
        previous.since if previous else time.time(),
    )
    path = _path(lemon_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(failure._asdict()))
        temporary.replace(path)
    except OSError as error:
        _log.warning("could not record the scout failure of %s: %s", lemon_id, error)
    return failure


def clear(lemon_id: str) -> None:
    try:
        _path(lemon_id).unlink(missing_ok=True)
    except OSError as error:
        _log.warning("could not clear the scout failure record of %s: %s", lemon_id, error)


def failing(lemon_id: str) -> Failure | None:
    found = read(lemon_id)
    return found if found and found.count >= FAILING_AFTER else None


def delay(lemon_id: str, base: float) -> float:
    """Seconds before the next attempt: *base*, doubling with each failure in a row."""
    found = read(lemon_id)
    return min(base * 2 ** max(0, found.count - 1), _MAX_DELAY) if found else base


def describe(failure: Failure) -> str:
    since = dt.datetime.fromtimestamp(failure.since).strftime("%H:%M")
    return f"{failure.reason} ({failure.count} attempts in a row since {since})"
