"""Whether the inbox's attention mode is on: `inbox.json` in lemonaid's state directory.

It is per machine, like the grove's layout, and starts off. Read and write it off the event loop.
"""

import json
import os
import tempfile
import threading
from collections import abc
from pathlib import Path

from ..config import TuiConfig
from ..log import get_logger
from . import order

_log = get_logger("inbox.attention")
_saving = threading.Lock()


def path() -> Path:
    state = Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid").expanduser()
    return state / "inbox.json"


def _read(target: Path) -> dict:
    try:
        data = json.loads(target.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        _log.warning("unreadable inbox state at %s, starting from nothing: %s", target, error)
        return {}

    return data if isinstance(data, dict) else {}


def load(where: Path | None = None) -> bool:
    return bool(_read(where or path()).get("attention", False))


def save(on: bool, where: Path | None = None) -> None:
    target = where or path()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {**_read(target), "attention": on}
    with tempfile.NamedTemporaryFile("w", dir=target.parent, delete=False, suffix=".tmp") as out:
        json.dump(data, out, indent=1, sort_keys=True)
    os.replace(out.name, target)


def save_latest(latest: abc.Callable[[], bool], where: Path | None = None) -> None:
    """Save *latest*'s value once no other save is running. Saves started in any order
    then leave the newest choice on disk, as long as each starts after its choice is made.
    """
    with _saving:
        save(latest(), where)


def rule(tui: TuiConfig, on: bool) -> order.FoldRule | None:
    """Attention mode's rule while it is on, which replaces `fold_statuses`."""
    if on:
        return order.attention_rule(tui.attention_statuses)

    return order.status_rule(tui.fold_statuses)
