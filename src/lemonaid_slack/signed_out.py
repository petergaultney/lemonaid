"""What happens when lemonaid has no Slack session it can use: one inbox row for the user, and
Slack calls paused until a new sign-in.

A session Slack refused is marked here by its `captured_at`, so the scouts and the gateway stop
calling Slack with it; a sign-in saves a new session, which the mark no longer matches.
"""

import fcntl
import json
import time
from pathlib import Path

from . import host, session, wakes

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
    host.lemonaid("inbox", "add", CHANNEL, message, "--name", "slack")


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
        host.write_json(path, {"captured_at": captured, "at": time.time()})
    _post(problem(current) or f"Slack refused your lemons' sign-in; {SIGN_IN}")


def signed_in() -> None:
    """Clear the pause and the inbox row after a new sign-in."""
    _mark_path().unlink(missing_ok=True)
    host.lemonaid("inbox", "archive", "--channel", CHANNEL)
