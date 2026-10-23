"""Where the grove view was last panned to, so the grove opens there again.

Kept apart from the layout: it changes with every pan, and the layout only when a block or
tree arrives or moves.
"""

import json
import os
import tempfile
from pathlib import Path

from ...log import get_logger
from . import state

_log = get_logger("grove.view")


def _path() -> Path:
    return state.path().with_name("grove-view.json")


def load() -> tuple[float, float]:
    try:
        x, y = json.loads(_path().read_text())["pan"]
        return float(x), float(y)
    except FileNotFoundError:
        return 0.0, 0.0
    except (OSError, ValueError, KeyError, TypeError) as error:
        _log.warning("unreadable grove view at %s, starting at the top left: %s", _path(), error)
        return 0.0, 0.0


def save(pan: tuple[float, float]) -> None:
    target = _path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=target.parent, delete=False, suffix=".tmp") as out:
        json.dump({"pan": list(pan)}, out)
    os.replace(out.name, target)
