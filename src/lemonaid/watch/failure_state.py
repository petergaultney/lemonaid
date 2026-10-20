"""Remember source failures until they recover, without repeating them on rearm."""

import hashlib
import json
from collections import abc
from pathlib import Path

from . import cursors, subscriptions


def path(root: Path, spec: subscriptions.Subscription, reason: str) -> Path:
    key = hashlib.sha256(repr(spec.key).encode()).hexdigest()[:16]
    return root / "failures" / f"{key}.{reason}.json"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def report(
    path: Path, message: str, deliver: abc.Callable[[str], object], threshold: int = 1
) -> int:
    """The consecutive failures so far, this one included."""
    saved = _load(path)
    attempts = int(saved.get("attempts", 0)) + 1
    previous = str(saved.get("reported", ""))
    cursors.write_json(path, {"attempts": attempts, "reported": previous})
    if attempts >= threshold and previous != message:
        deliver(message)
        cursors.write_json(path, {"attempts": attempts, "reported": message})
    return attempts


def clear(path: Path) -> None:
    path.unlink(missing_ok=True)
