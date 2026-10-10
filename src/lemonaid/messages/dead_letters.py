"""A log of every message `tell` queued for a lemon that won't read it.

One JSON object per line, written when the message is sent, so whoever
minds the lemons can watch the file instead of asking each sender.
"""

import json
import time
from pathlib import Path

from ..log import get_logger
from . import store

_log = get_logger("messages.dead_letters")


def path() -> Path:
    return store.inbox_root() / "dead-letters.jsonl"


def record(sender: str, lemon_id: str, state: str, said: str, message: Path) -> None:
    """Append one entry; *said* is the line `tell` printed to the sender."""
    entry = {
        "at": time.time(),
        "from": sender,
        "to": lemon_id,
        "state": state,
        "said": said,
        "message": str(message),
    }
    try:
        path().parent.mkdir(parents=True, exist_ok=True)
        with open(path(), "a") as log:
            log.write(json.dumps(entry) + "\n")
    except OSError as error:
        _log.warning("Could not log the dead letter to %s: %s", path(), error)
