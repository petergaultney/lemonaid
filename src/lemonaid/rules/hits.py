"""The log of every match the end-of-turn check finds, and which of them are reported.

A lemon is reported once a day per pattern, and all lemons together at most 20 times an
hour; a match past either limit is only logged. The first report after the hourly
limit says how many matches it held.
"""

import contextlib
import datetime as dt
import fcntl
import json
import typing as ty
from collections import abc
from pathlib import Path

from ..log import get_logger
from . import snapshot

_log = get_logger("rules.hits")

REPORTED, REPEAT, HELD, LOGGED = "reported", "repeat", "held", "logged"
_DAY = 24 * 3600.0
_HOUR = 3600.0
_HOURLY = 20


class Hit(ty.NamedTuple):
    channel: str
    pattern: str
    mode: str
    harness: str
    cwd: str
    transcript: str
    excerpt: str


class Outcome(ty.NamedTuple):
    outcome: str  # REPORTED, REPEAT, HELD or LOGGED
    held: int  # for a report: matches the hourly limit held since the last report


def path() -> Path:
    return snapshot.rules_dir() / "hits.jsonl"


@contextlib.contextmanager
def _locked() -> abc.Iterator[None]:
    lock = path().with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        yield


def _entries() -> abc.Iterator[dict]:
    try:
        lines = path().read_text().splitlines()
    except FileNotFoundError:
        return

    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            _log.warning("skipped a line of %s that isn't JSON", path())
            continue
        if isinstance(entry, dict) and isinstance(entry.get("at"), str):
            yield {**entry, "at": dt.datetime.fromisoformat(entry["at"]).timestamp()}


def _decide(entries: abc.Sequence[dict], hit: Hit, now: float) -> Outcome:
    reported = [entry for entry in entries if entry.get("outcome") == REPORTED]
    if any(
        (entry.get("channel"), entry.get("pattern")) == (hit.channel, hit.pattern)
        and now - entry["at"] < _DAY
        for entry in reported
    ):
        return Outcome(REPEAT, 0)

    if sum(now - entry["at"] < _HOUR for entry in reported) >= _HOURLY:
        return Outcome(HELD, 0)

    last = max((entry["at"] for entry in reported), default=0.0)
    return Outcome(
        REPORTED, sum(entry.get("outcome") == HELD and entry["at"] > last for entry in entries)
    )


def record(hit: Hit, now: float, reporting: bool) -> Outcome:
    """Log *hit*, and decide whether it is reported; *reporting*: there is someone to report to."""
    with _locked():
        outcome = _decide(list(_entries()), hit, now) if reporting else Outcome(LOGGED, 0)
        with path().open("a") as log:
            at = dt.datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds")
            log.write(json.dumps({"at": at, **hit._asdict(), "outcome": outcome.outcome}) + "\n")
    return outcome
