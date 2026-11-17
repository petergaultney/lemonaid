"""The size of the grove screen the last time one was open, which a lemon arranging the grove
from a command line can't ask for: its own terminal is not that screen.
"""

import json

from ...log import get_logger
from . import state

_log = get_logger("grove.screen_size")


def _file():
    return state.path().with_name("grove-screen.json")


def last() -> tuple[int, int] | None:
    try:
        width, height = json.loads(_file().read_text())["size"]
    except (OSError, ValueError, KeyError, TypeError):
        return None

    return (width, height) if isinstance(width, int) and isinstance(height, int) else None


def record(size: tuple[int, int]) -> None:
    if last() == size:
        return

    try:
        _file().parent.mkdir(parents=True, exist_ok=True)
        _file().write_text(json.dumps({"size": list(size)}))
    except OSError as error:
        _log.warning("can't record the grove screen's size: %s", error)
