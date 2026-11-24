"""A session's context window: the doc sections it has been given since the window
began, and how many tool calls it has made.

A window begins when a session starts, is cleared or is compacted; a resume continues
it. Its state is kept in `paths.window()` and locked while a hook changes it, since a
lemon's parallel tool calls run their hooks at the same time.
"""

import contextlib
import fcntl
import json
from collections import abc
from pathlib import Path

from ..log import get_logger
from . import paths

_log = get_logger("docs.window")

REMIND_AFTER = 30  # tool calls since a section was delivered before a match repeats its reminder


def _read(path: Path) -> dict:
    try:
        state = json.loads(path.read_text())
    except FileNotFoundError:
        state = {}
    except (OSError, ValueError) as e:
        _log.warning("starting %s over: %s", path, e)
        state = {}
    if not isinstance(state, dict):
        state = {}
    return {"window": 0, "calls": 0, "delivered": {}, "packages": [], **state}


@contextlib.contextmanager
def opened(harness: str, session: str) -> abc.Iterator[dict]:
    """The session's window state, saved when the block ends."""
    path = paths.window(harness, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _read(path)
        yield state
        path.write_text(json.dumps(state))


def begin(state: dict, source: str, packages: abc.Sequence[str]) -> bool:
    """Start a new window given *packages*, unless *source* is a resume of the current one,
    which keeps the packages it was given; whether it did."""
    if source == "resume" and state["window"]:
        return False

    state["window"] += 1
    state["delivered"] = {}
    state["packages"] = list(packages)
    return True


def delivery(state: dict, key: str, mtime: float, reminder: bool, whole: str, before: bool) -> str:
    """How a match gives the section *key* (in the doc whose own key is *whole*) now.

    - `full` when this window hasn't had it, or the doc changed since; `refuse` instead
      for a *before* trigger, whose first match is refused even when a package carried
      the doc.
    - `reminder` (when the doc has one) for a doc a package carried, at its first match,
      and once REMIND_AFTER calls have passed since a match last gave it.
    - "" otherwise.
    """
    given = state["delivered"].get(key) or ({} if before else state["delivered"].get(whole))
    if before and isinstance(given, dict) and given.get("call") is None:
        given = {}
    if not isinstance(given, dict) or given.get("mtime") != mtime:
        return "refuse" if before else "full"
    if given.get("call") is None or state["calls"] - given["call"] >= REMIND_AFTER:
        return "reminder" if reminder else ""

    return ""


def given(state: dict, key: str, mtime: float, package: bool) -> None:
    """Record *key* as given now; a package's doc has no call, so its triggers still
    give their reminder at the action."""
    state["delivered"][key] = {"mtime": mtime, "call": None if package else state["calls"]}
