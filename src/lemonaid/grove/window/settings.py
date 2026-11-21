"""What the grove window remembers between runs: each view's pan and zoom, the label sizes, and
where it was left with each set of displays, when that was away from the terminal.

Kept by Python in lemonaid's state directory, since the page's own storage doesn't outlive a run.
The page and the window's frame are saved from different threads, so each save merges into what's
there under a lock.
"""

import json
import threading
from collections import abc
from pathlib import Path

from ...log import get_logger
from ..layout import state

_log = get_logger("grove.window")
_saving = threading.Lock()


def path() -> Path:
    return state.path().with_name("grove-window.json")


def load(where: Path | None = None) -> dict:
    try:
        return json.loads((where or path()).read_text())
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        _log.warning("ignoring unreadable %s", where or path())
        return {}


def _change(changed: abc.Callable[[dict], dict], where: Path | None) -> None:
    target = where or path()
    with _saving:
        written = target.with_suffix(".tmp")
        target.parent.mkdir(parents=True, exist_ok=True)
        written.write_text(json.dumps(changed(load(target))))
        written.replace(target)


def update(changes: dict, where: Path | None = None) -> None:
    """Replace the top-level keys in *changes*, keeping the rest."""
    _change(lambda kept: kept | changes, where)


def frame(displays: str, where: Path | None = None) -> list[float] | None:
    """The window's frame, (x, y, w, h) as AppKit has it, last left with *displays* connected."""
    return load(where).get("frames", {}).get(displays)


def keep_frame(displays: str, placed: list[float], where: Path | None = None) -> None:
    _change(lambda kept: kept | {"frames": kept.get("frames", {}) | {displays: placed}}, where)


def forget_frame(displays: str, where: Path | None = None) -> None:
    """With these displays the window goes back over the terminal."""
    _change(
        lambda kept: kept
        | {"frames": {d: f for d, f in kept.get("frames", {}).items() if d != displays}},
        where,
    )
