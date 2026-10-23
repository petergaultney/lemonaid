"""Where the grove keeps its layout: `grove.json` in lemonaid's state directory.

It holds each block's plot and each tree's spot and letter, so they stay put across restarts.
It is per machine, like pins and group order.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ...log import get_logger

_log = get_logger("grove.state")
VERSION = 1


def path() -> Path:
    state = Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid").expanduser()
    return state / "grove.json"


def load(where: Path | None = None) -> dict[str, Any]:
    target = where or path()
    try:
        data = json.loads(target.read_text())
    except FileNotFoundError:
        return {"version": VERSION, "plots": {}, "trees": {}}
    except (OSError, json.JSONDecodeError) as error:
        _log.warning("unreadable grove layout at %s, starting a new one: %s", target, error)
        return {"version": VERSION, "plots": {}, "trees": {}}

    return {
        "version": VERSION,
        "plots": data.get("plots", {}),
        "trees": data.get("trees", {}),
        **{key: data[key] for key in ("roads", "stream") if key in data},
    }


def save(data: dict[str, Any], where: Path | None = None) -> None:
    target = where or path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=target.parent, delete=False, suffix=".tmp") as out:
        json.dump(data, out, indent=1, sort_keys=True)
    os.replace(out.name, target)
