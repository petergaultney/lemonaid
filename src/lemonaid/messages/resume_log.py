"""When `tell` last started each lemon, kept beside its inbox.

A resumed harness takes seconds to come up and report its new terminal, and
until it does the next `tell` still sees it as dead.
"""

import time
from pathlib import Path

STARTING_SECONDS = 60.0


def _path(inbox: Path) -> Path:
    return inbox / ".autoresumed"


def last_start(inbox: Path) -> float | None:
    try:
        lines = _path(inbox).read_text().split()
    except FileNotFoundError:
        return None

    try:
        return float(lines[-1]) if lines else None
    except ValueError:
        return None


def starting(inbox: Path, now: float) -> bool:
    """Whether a start within the last minute may still be coming up."""
    started = last_start(inbox)
    return started is not None and now - started < STARTING_SECONDS


def record(inbox: Path) -> None:
    inbox.mkdir(parents=True, exist_ok=True)
    with open(_path(inbox), "a") as log:
        log.write(f"{time.time()}\n")
