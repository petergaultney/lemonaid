"""When `tell` started each lemon, and which of those starts failed, kept beside its inbox.

A resumed harness takes seconds to come up and report its new terminal, and
until it does the next `tell` still sees it as dead. One that is dead again a
little later never came up, or crashed: that start counts twice against the
limit, so a crash loop is refused sooner.
"""

import time
import typing as ty
from collections import abc
from pathlib import Path

STARTING_SECONDS = 60.0
_QUICK_DEATH_SECONDS = 180.0  # dead again this soon after a start: the start failed

START = "start"
FAILED = "failed"


class Entry(ty.NamedTuple):
    at: float
    kind: str


def _path(inbox: Path) -> Path:
    return inbox / ".autoresumed"


def _parse(line: str) -> Entry | None:
    at, _, kind = line.partition(" ")
    try:
        return Entry(float(at), kind or START)
    except ValueError:
        return None


def entries(inbox: Path) -> list[Entry]:
    try:
        lines = _path(inbox).read_text().splitlines()
    except FileNotFoundError:
        return []

    return [entry for line in lines if (entry := _parse(line))]


def starting(log: abc.Sequence[Entry], now: float) -> bool:
    """Whether the last start, within the last minute, may still be coming up."""
    return bool(log) and log[-1].kind == START and now - log[-1].at < STARTING_SECONDS


def died_quickly(log: abc.Sequence[Entry], now: float) -> bool:
    """Whether a lemon found dead now was dead again soon after its last start."""
    return bool(log) and log[-1].kind == START and now - log[-1].at < _QUICK_DEATH_SECONDS


def within(log: abc.Iterable[Entry], now: float, window: float) -> int:
    return sum(1 for entry in log if now - entry.at < window)


def record(inbox: Path, kind: str = START) -> None:
    inbox.mkdir(parents=True, exist_ok=True)
    with open(_path(inbox), "a") as log:
        log.write(f"{time.time()} {kind}\n")
