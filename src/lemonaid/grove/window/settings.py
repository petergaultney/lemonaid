"""What the grove window remembers between runs: each view's pan and zoom, and the label sizes.

Kept by Python in lemonaid's state directory, since the page's own storage doesn't outlive a run.
"""

import json
from pathlib import Path

from ...log import get_logger
from ..layout import state

_log = get_logger("grove.window")


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


def save(settings: dict, where: Path | None = None) -> None:
    target = where or path()
    target.parent.mkdir(parents=True, exist_ok=True)
    written = target.with_suffix(".tmp")
    written.write_text(json.dumps(settings))
    written.replace(target)
