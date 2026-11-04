"""Read receipts: whether a message `tell` sent is still waiting or was received.

A message's ID is its file's name without `.md`, unique across every mailbox, so a receipt
follows a message through a reroll's forward without knowing which mailbox took it. A
sender that gave `store.send` a key finds its latest message by that key instead, and
`resend` replaces an unreceived copy without racing the lemon receiving it.
"""

import contextlib
import datetime
from collections import abc
from pathlib import Path

from .. import home
from . import store

PENDING = "pending"
UNKNOWN = "unknown"


def message_id(path: Path) -> str:
    return path.stem


def _receipt(pending: abc.Iterable[Path], received: abc.Iterable[Path]) -> str:
    if any(True for _ in pending):
        return PENDING

    times = [path.stat().st_mtime for path in received]
    if not times:
        return UNKNOWN

    at = datetime.datetime.fromtimestamp(max(times), datetime.UTC)
    return f"delivered {at.isoformat(timespec='seconds')}"


def _plain(name: str) -> bool:
    return bool(name) and "/" not in name and not name.startswith(".") and "*" not in name


def receipt(message: str) -> str:
    """`pending` while the message waits in a mailbox, `delivered <time>` once its lemon
    received it, or `unknown` when no mailbox holds it."""
    if not _plain(message):
        return UNKNOWN

    root = store.mailbox_root()
    return _receipt(root.glob(f"*/{message}.md"), root.glob(f"*/done/{message}.md"))


def by_key(key: str) -> str:
    """The receipt for the messages sent with *key*: `pending` while any waits."""
    if not _plain(key):
        return UNKNOWN

    root = store.mailbox_root()
    return _receipt(root.glob(f"*/*-{key}.md"), root.glob(f"*/done/*-{key}.md"))


def resend(mailbox: Path, key: str, send: abc.Callable[[], Path]) -> bool:
    """Run *send*, which sends with *key* to *mailbox*, unless a message with *key* was
    received; any copy still waiting is removed first. Holds the receive lock of every
    mailbox involved, so no receiver takes a copy between the check and the replacement.
    Returns whether it sent."""
    if not _plain(key):
        raise ValueError(f"Not a message key: {key!r}")

    with home.guard.operation(), contextlib.ExitStack() as locks:
        root = store.mailbox_root()
        held = {path.parent for path in root.glob(f"*/*-{key}.md")} | {store.forwarded(mailbox)}
        for box in sorted(held):
            locks.enter_context(store.receive_lock(box))
        if by_key(key).startswith("delivered"):
            return False

        for path in root.glob(f"*/*-{key}.md"):
            path.unlink(missing_ok=True)
        send()
    return True
