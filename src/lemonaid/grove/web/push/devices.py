"""The devices that turned push notifications on, and the server's signing key, kept beside the
inbox database: never in a checkout, and redirected with it (`LEMONAID_DB`)."""

import json
import os
import threading
from pathlib import Path

from ....inbox import db
from . import webpush

_lock = threading.Lock()  # the server's threads share the file


def _dir() -> Path:
    return db.get_db_path().parent / "push"


def key() -> bytes:
    """The VAPID private key, made on first use, readable only by its owner."""
    path = _dir() / "vapid.pem"
    with _lock:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(webpush.new_key())
        return path.read_bytes()


def _path() -> Path:
    return _dir() / "devices.json"


def _read() -> list[dict]:
    try:
        found = json.loads(_path().read_text())
    except FileNotFoundError:
        return []

    return found if isinstance(found, list) else []


def _write(entries: list[dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(entries, indent=2))
    temporary.replace(path)


def _device(entry: dict) -> webpush.Subscription:
    return webpush.Subscription(entry["endpoint"], entry["keys"]["p256dh"], entry["keys"]["auth"])


def all_devices() -> list[webpush.Subscription]:
    with _lock:
        return [_device(e) for e in _read()]


def find(endpoint: str) -> webpush.Subscription | None:
    return next((d for d in all_devices() if d.endpoint == endpoint), None)


def add(subscription: dict) -> webpush.Subscription:
    """Keep a browser's `PushSubscription.toJSON()`, replacing one with its endpoint. Raises
    ValueError for one that isn't."""
    try:
        entry = {
            "endpoint": str(subscription["endpoint"]),
            "keys": {k: str(subscription["keys"][k]) for k in ("p256dh", "auth")},
        }
    except (KeyError, TypeError) as error:
        raise ValueError(f"not a push subscription: {error}") from error

    if not entry["endpoint"].startswith("https://"):
        raise ValueError("a push endpoint is an https address")
    webpush.check(_device(entry))

    with _lock:
        _write([e for e in _read() if e.get("endpoint") != entry["endpoint"]] + [entry])
    return _device(entry)


def remove(endpoint: str) -> bool:
    with _lock:
        entries = _read()
        kept = [e for e in entries if e.get("endpoint") != endpoint]
        _write(kept)
    return len(kept) != len(entries)
