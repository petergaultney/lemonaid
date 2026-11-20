"""The files the Slack gateway and the thread scouts share, under lemonaid's state directory.

    slack/threads/<channel>/<ts>/wake     touched by the gateway when the socket sees a message
                                          in that thread; the scouts following it watch it
    slack/threads/<channel>/<ts>/<lemon>  touched by each scout as it polls, so the gateway
                                          forwards events only for threads someone follows
    slack/gateway.alive                   touched while the gateway's socket is up
    slack/session.generation              touched whenever the saved session is replaced or
                                          removed, so an open socket stops using the old one

A thread's files are the whole contract: the gateway never knows which lemon follows what.
"""

import os
import time
from pathlib import Path

from ..watch import cursors

INTEREST = 300.0  # a scout polls at least this often while it follows a thread
_ALIVE = 60.0  # the gateway beats more often than this while its socket is up
_FORGET = 86400.0


def state_dir() -> Path:
    return cursors.root().parent / "slack"


def _thread_dir(channel: str, ts: str) -> Path:
    return state_dir() / "threads" / channel / ts


def wake_path(channel: str, ts: str) -> Path:
    return _thread_dir(channel, ts) / "wake"


def wake_file(channel: str, ts: str) -> Path:
    """The thread's wake file, created if missing: a kqueue watch opened on a path whose
    directory does not exist yet would never see it appear."""
    path = wake_path(channel, ts)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return path


def follow(channel: str, ts: str, follower: str) -> None:
    """Mark *follower*'s interest in the thread now."""
    (wake_file(channel, ts).parent / follower).touch()


def stamp(channel: str, ts: str) -> int:
    """Changes each time the gateway signals the thread; 0 before it ever has."""
    try:
        return wake_path(channel, ts).stat().st_mtime_ns
    except FileNotFoundError:
        return 0


def followed(now: float) -> set[tuple[str, str]]:
    """(channel, ts) of every thread a scout polled within `INTEREST`; forgets long-idle ones."""
    found = set()
    for path in state_dir().glob("threads/*/*/*"):
        if path.name == "wake":
            continue
        try:
            age = now - path.stat().st_mtime
        except FileNotFoundError:
            continue
        if age > _FORGET:
            path.unlink(missing_ok=True)
        elif age < INTEREST:
            found.add((path.parent.parent.name, path.parent.name))
    return found


def signal(channel: str, ts: str) -> bool:
    """Wake the scouts following the thread; False when nobody follows it."""
    try:
        os.utime(wake_path(channel, ts))
    except FileNotFoundError:
        return False

    return True


def beat() -> None:
    path = state_dir() / "gateway.alive"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()))


def went_down() -> None:
    (state_dir() / "gateway.alive").unlink(missing_ok=True)


def gateway_up(now: float | None = None) -> bool:
    """Whether a gateway's socket is up, so a scout need not fetch on a timer."""
    try:
        age = (now or time.time()) - (state_dir() / "gateway.alive").stat().st_mtime
    except FileNotFoundError:
        return False

    return age < _ALIVE


def _generation_path() -> Path:
    return state_dir() / "session.generation"


def session_changed() -> None:
    path = _generation_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(time.time()))


def session_generation() -> str:
    try:
        return _generation_path().read_text()
    except FileNotFoundError:
        return ""
