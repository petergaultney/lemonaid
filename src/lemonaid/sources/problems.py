"""A watch source's `problem` (Slack signed out, say), told to a lemon once per lapse: not again
until one of that source's polls for the lemon succeeds."""

import contextlib
import fcntl
import json
import time
from collections import abc
from pathlib import Path

from ..watch import cursors

_CLAIM = 600.0  # a claim older than this is from a scout that died delivering


def _notices(root: Path, source: str) -> Path:
    return root / "failures" / f"{source}-problem.json"


@contextlib.contextmanager
def _locked(path: Path) -> abc.Iterator[dict]:
    """*path*'s saved notices, held under its lock; the caller's changes are written back."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            saved = json.loads(path.read_text())
        except (OSError, ValueError):
            saved = {}
        saved = saved if isinstance(saved, dict) else {}
        yield saved
        cursors.write_json(path, saved)


def tell_once(root: Path, source: str, message: str, deliver: abc.Callable[[str], object]) -> None:
    """Deliver *message* to the lemon whose cursors are in *root*, unless it has had a notice
    from *source* since that source last answered: one per lapse, whatever its wording, so a
    reworded notice from a newer plugin, or one from another process, is not news.

    A lemon's subscriptions to one source run at once. The one that claims the notice delivers
    it after releasing the lock, since its siblings must finish their polls for the batch to
    go, and marks it heard only once delivery succeeds; a failed delivery frees the claim, and
    so does a scout that died holding it for `_CLAIM`.
    """
    path = _notices(root, source)
    with _locked(path) as saved:
        claimed = "claimed" in saved and time.time() - saved.get("at", 0) < _CLAIM
        if "told" in saved or claimed:
            return

        saved.update(claimed=message, at=time.time())
    delivered = False
    try:
        deliver(message)
        delivered = True
    finally:
        with _locked(path) as saved:
            if saved.get("claimed") == message:
                del saved["claimed"], saved["at"]
            if delivered:
                saved["told"] = message


def heard_again(root: Path, source: str) -> None:
    """A poll worked, so the next problem is news to this lemon."""
    _notices(root, source).unlink(missing_ok=True)
