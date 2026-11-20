"""What happens when lemonaid has no Slack session it can use: one inbox row for the user, and
Slack calls paused until a new sign-in.

A session Slack refused is marked here by its `captured_at`, so the scouts and the gateway stop
calling Slack with it; a sign-in saves a new session, which the mark no longer matches.
"""

import contextlib
import fcntl
import json
import time
from collections import abc
from pathlib import Path

from ..inbox import db, ended
from ..watch import cursors
from . import session, wakes

CHANNEL = "lemonaid:slack"
SIGN_IN = "run `lemonaid slack signin`"
_CLAIM = 600.0  # a claim older than this is from a scout that died delivering


def _mark_path() -> Path:
    return wakes.state_dir() / "refused.json"


def refused(current: session.Session) -> bool:
    try:
        return json.loads(_mark_path().read_text()).get("captured_at") == current.captured_at
    except (OSError, ValueError, AttributeError):
        return False


def _reason(current: session.Session | None) -> str:
    if current is None:
        return "Slack is not signed in for your lemons"

    if refused(current):
        return "Slack no longer accepts the sign-in your lemons use"

    return ""


def problem(current: session.Session | None) -> str:
    """Why lemonaid can't read Slack now, and what the user runs; or ""."""
    return f"{why}; {SIGN_IN}" if (why := _reason(current)) else ""


def lemon_problem(current: session.Session | None) -> str:
    """`problem`, for a lemon: only its user can open the sign-in window."""
    ask = "ask your user to run `lemonaid slack signin`; your brief's lines resume once they have"
    return f"{why}: {ask}" if (why := _reason(current)) else ""


def _post(message: str) -> None:
    with db.connect() as conn:
        db.add(conn, CHANNEL, message, name="slack")


def mark(current: session.Session | None) -> None:
    """Pause Slack calls with *current* (None: there is no session) and tell the user, once."""
    path = _mark_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / "refused.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        captured = current.captured_at if current else None
        try:
            if json.loads(path.read_text()).get("captured_at") == captured:
                return
        except (OSError, ValueError, AttributeError):
            pass
        cursors.write_json(path, {"captured_at": captured, "at": time.time()})
    _post(problem(current) or f"Slack refused your lemons' sign-in; {SIGN_IN}")


def signed_in() -> None:
    """Clear the pause and the inbox row after a new sign-in."""
    _mark_path().unlink(missing_ok=True)
    with db.connect() as conn:
        db.archive_channel(conn, CHANNEL, "signed in to Slack", cause=ended.ARCHIVED, by="slack")


def _notices(root: Path) -> Path:
    return root / "failures" / "slack-signin.json"


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


def tell_once(root: Path, message: str, deliver: abc.Callable[[str], object]) -> None:
    """Deliver *message* to the lemon whose cursors are in *root*, unless it has had a notice
    since Slack last answered: one per lapse, whatever its wording, so a reworded notice from a
    newer lemonaid, or one from another process, is not news.

    A lemon's Slack scouts run at once. The one that claims the notice delivers it after
    releasing the lock, since its siblings must finish their polls for the batch to go, and
    marks it heard only once delivery succeeds; a failed delivery frees the claim, and so does
    a scout that died holding it for `_CLAIM`.
    """
    path = _notices(root)
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


def heard_again(root: Path) -> None:
    """A Slack call worked, so the next refusal is news to this lemon."""
    _notices(root).unlink(missing_ok=True)
