"""The tmux servers whose tab labels the scout host keeps, one file per server socket."""

import hashlib
import json
import os
import pathlib

from ..log import get_logger

_log = get_logger("tmux.label_servers")


def _dir() -> pathlib.Path:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return pathlib.Path(state).expanduser() / "tmux-labels"


def _path(socket: str) -> pathlib.Path:
    return _dir() / f"{hashlib.sha256(socket.encode()).hexdigest()[:16]}.json"


def register(socket: str) -> None:
    _dir().mkdir(parents=True, exist_ok=True)
    path = _path(socket)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps({"socket": socket}))
    temporary.replace(path)


def listed() -> set[str]:
    found = set()
    for path in _dir().glob("*.json"):
        try:
            found.add(json.loads(path.read_text())["socket"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            _log.warning("unreadable tmux label registration %s: %s", path, error)
    return found


def remove(socket: str) -> None:
    _path(socket).unlink(missing_ok=True)
