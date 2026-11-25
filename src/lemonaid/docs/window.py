"""A session's context window: the doc sections it has been given since the window
began, and how many tool calls it has made.

A window begins when a session starts, is cleared or is compacted; a resume continues
it, unless the session's docs mode changed since. Docs a Claude lemon was launched with are in its system prompt, which no compaction
removes, so every window counts them as given. Its state is kept in `paths.window()` and locked while a hook changes it, since a
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
    return {
        "window": 0,
        "calls": 0,
        "delivered": {},
        "shadowed": {},  # the same, for what the lemon's mode only logged
        "packages": [],
        "mode": "",  # the docs mode the window began in, which its hooks keep to
        "prompt": {},  # doc key -> mtime, for the docs in a Claude lemon's system prompt
        "lemon": {},  # what the session start learned about the lemon (`facts`)
        **state,
    }


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


def begin(state: dict, source: str, mode: str, packages: abc.Sequence[str]) -> bool:
    """Start a new window in *mode* given *packages*, unless *source* is a resume of the
    current one in the same mode, which keeps what it was given; whether it did."""
    if source == "resume" and state["window"] and state["mode"] == mode:
        return False

    state["window"] += 1
    state["mode"] = mode
    state["delivered"] = {
        key: {"mtime": mtime, "call": None} for key, mtime in state["prompt"].items()
    }
    state["shadowed"] = {}
    state["packages"] = list(packages)
    return True


def joined(state: dict, packages: abc.Iterable[str]) -> None:
    """Count *packages* among the window's, once each."""
    state["packages"] = list(dict.fromkeys([*state["packages"], *packages]))


def ledger(shadow: bool) -> str:
    """Where a window records what it gave: what was only logged is kept apart, so it
    never stands in for a real delivery."""
    return "shadowed" if shadow else "delivered"


def delivery(
    state: dict,
    key: str,
    mtime: float,
    reminder: bool,
    whole: str,
    before: bool,
    shadow: bool = False,
) -> str:
    """How a match gives the section *key* (in the doc whose own key is *whole*) now.

    - `full` when this window hasn't had it, or the doc changed since; `refuse` instead
      for a *before* trigger, whose first match is refused even when a package carried
      the doc.
    - `reminder` (when the doc has one) for a doc a package carried, at its first match,
      and once REMIND_AFTER calls have passed since a match last gave it.
    - "" otherwise.
    """
    book = state[ledger(shadow)]
    given = book.get(key) or ({} if before else book.get(whole))
    if before and isinstance(given, dict) and given.get("call") is None:
        given = {}
    if not isinstance(given, dict) or given.get("mtime") != mtime:
        return "refuse" if before else "full"
    if given.get("call") is None or state["calls"] - given["call"] >= REMIND_AFTER:
        return "reminder" if reminder else ""

    return ""


def given(state: dict, key: str, mtime: float, package: bool, shadow: bool = False) -> None:
    """Record *key* as given now; a package's doc has no call, so its triggers still
    give their reminder at the action."""
    state[ledger(shadow)][key] = {"mtime": mtime, "call": None if package else state["calls"]}
