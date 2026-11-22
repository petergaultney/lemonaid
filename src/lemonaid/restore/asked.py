"""The lost lemons a person asked for while a restore runs, which it starts before the rest.

Showing a lost lemon from the inbox, the grove or `lemonaid go` would otherwise resume it
alongside the restore, or fail to find its pane. Instead the ask goes into a file beside
the restore lock, which the running restore reads each time it picks the next lemon.
"""

import os
import pathlib
import typing as ty
from collections import abc

from ..inbox import ended
from ..log import get_logger
from . import auto

_log = get_logger("restore.asked")


def _path() -> pathlib.Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return pathlib.Path(state).expanduser() / "restore-asked"


def channels() -> frozenset[str]:
    """The channels asked for since this restore began."""
    try:
        return frozenset(_path().read_text().split())
    except FileNotFoundError:
        return frozenset()
    except OSError as e:
        _log.warning("could not read what was asked of restore: %s", e)
        return frozenset()


def clear() -> None:
    _path().unlink(missing_ok=True)


def ask(channel: str, metadata: abc.Mapping[str, ty.Any], name: str) -> str:
    """Have the running restore start *channel*'s lemon next, when it is one restore brings
    back: what to tell the person who asked, or "" when no restore is bringing it back."""
    if not ended.revivable(metadata) or not auto.running():
        return ""

    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as asks:
        asks.write(channel + "\n")
    return f"{name or channel} is still lost; the restore running now starts it next"
