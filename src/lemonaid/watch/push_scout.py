"""A Claude lemon's scout: `lemonaid watch --self --push`, detached, for as long as its session runs.

It delivers each batch of `watch --self` through the session's inbox socket instead of
exiting with it, so the lemon keeps no background task. It holds the same lock as
`watch --self`, so the Stop check counts it as the lemon's waiter, and a second one for
the same Lemon-ID refuses to start.
"""

import contextlib
import logging
import os
import pathlib
import subprocess
import sys
import time
from collections import abc

from ..claude import inbound, session_socket
from ..inbox.channel import channel_id
from ..launch.restart import gates
from ..log import get_logger
from . import deaf_waiter, delivery, registry, stop_sender, wait_state

_log = get_logger("watch.push_scout")

FLAG = "--push"
_INSTRUCTION = (
    "Read the changed sources and handle the entire batch. lemonaid is watching for you "
    "and pushes the next batch into this session."
)


def session(session_id: str, wait: float = 0) -> session_socket.Session | None:
    """The live session, waiting up to *wait* seconds for a starting one to list itself."""
    deadline = time.monotonic() + wait
    while (found := session_socket.find(session_id)) is None and time.monotonic() < deadline:
        time.sleep(0.5)
    return found


def problem(entry: session_socket.Session | None) -> str:
    """Why a scout can't push into *entry*, or ""."""
    if entry is None:
        return "no running Claude session with an inbox socket"

    if not inbound.session_accepts(entry):
        return 'the session would hold pushed messages; set "crossSessionInbound": "accept"'

    return ""


def to_session(entry: session_socket.Session) -> delivery.Deliver:
    def deliver(message: str) -> None:
        try:
            session_socket.send(entry, f"lemonaid watch event:\n\n{message}\n\n{_INSTRUCTION}")
        except session_socket.Refused as error:
            raise delivery.Failed(f"Claude session refused the batch ({error})") from error

    return gates.deliver(channel_id("claude", entry.session_id), deliver)


def _announced_marker(session_id: str) -> pathlib.Path:
    return pathlib.Path(_log_path()).parent / "announced" / session_id


def announce(entry: session_socket.Session) -> None:
    """Tell the lemon its scout is delivering, once per session; a restarted scout stays quiet."""
    marker = _announced_marker(entry.session_id)
    if marker.exists():
        return

    try:
        session_socket.send(
            entry,
            f"lemonaid push scout started: batches and messages now arrive in this session through "
            f"its socket ({entry.socket}). lemonaid is watching for you.",
        )
    except session_socket.Refused as error:
        _log.warning("could not announce the scout to %s: %s", entry.session_id, error)
        return

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


def not_pushing(session_id: str, lemon_id: str) -> str:
    """The loud notice for a lemon whose batches and messages will not be pushed, or "" if a waiter reads them."""
    if wait_state.is_armed(lemon_id):
        return ""

    why = problem(session(session_id)) or f"its scout did not start; see {_log_path()}"
    return (
        f"lemonaid is NOT pushing batches or messages into this session ({why}). "
        "Messages reach you only while a background waiter runs, so you must run it."
    )


def _scout_channels(lemon_id: str) -> set[str]:
    return {w.channel for w in registry.running_for("wait", lemon_id) if FLAG in w.command.split()}


def running(lemon_id: str, session_id: str = "") -> bool:
    """Whether a scout runs for the lemon, pushing into *session_id* when one is named."""
    channels = _scout_channels(lemon_id)
    return channel_id("claude", session_id) in channels if session_id else bool(channels)


@contextlib.contextmanager
def logged(
    lemon_id: str,
    entry: session_socket.Session,
    restarting: abc.Callable[[], bool] = lambda: False,
) -> abc.Iterator[None]:
    """One line when the scout starts and one when it exits, saying whether the exit was normal.

    Normal: its session ended, its brief was detached, it is restarting on request (see
    `restart`), or `lemonaid watch stop` stopped it.
    A scout killed outright logs only its start line.
    """
    fields = f"lemon={lemon_id} session={entry.session_id} pid={os.getpid()}"
    _log.info("push scout started: %s", fields)
    try:
        yield
    except SystemExit as stop:  # SIGTERM, raised by the registry's handler
        requested = stop_sender.requested(registry.entry(os.getpid()))
        reason = "lemonaid watch stop" if requested else "SIGTERM from outside lemonaid"
        _exit(fields, f"{reason} (code {stop.code})", requested)
        raise
    except KeyboardInterrupt:
        _exit(fields, "interrupted", True)
        raise
    except BaseException as error:
        _exit(fields, f"{type(error).__name__}: {error}", False)
        raise
    else:
        reason = (
            "restarting on request"
            if restarting()
            else "brief detached"
            if session_socket.alive(entry)
            else "session ended"
        )
        _exit(fields, reason, True)


def _exit(fields: str, reason: str, normal: bool) -> None:
    _log.log(
        logging.INFO if normal else logging.WARNING,
        "push scout exited %s: %s %s",
        "normally" if normal else "abnormally",
        fields,
        f"reason={reason!r}",
    )


def _log_path() -> str:
    state = os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid"
    return os.path.expanduser(f"{state}/push-scout.log")


def _spawn(entry: session_socket.Session) -> None:
    os.makedirs(os.path.dirname(_log_path()), exist_ok=True)
    with open(_log_path(), "a") as log:
        subprocess.Popen(
            [
                *(sys.executable, "-m", "lemonaid", "watch", "--self", FLAG, "--foreground"),
                *("--channel", channel_id("claude", entry.session_id)),
            ],
            cwd=entry.cwd or None,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )


@gates.scout
def ensure(session_id: str, lemon_id: str, grace: float = 3.0, wait: float = 0) -> bool:
    """Start a scout for the lemon in *session_id* unless a waiter already runs; whether one now does.

    A scout still pushing into the lemon's previous session (before `/clear` or a resume)
    exits once it notices, so this waits for its lock rather than counting it.
    """
    deaf_waiter.clear(lemon_id, channel_id("claude", session_id))
    previous = _scout_channels(lemon_id) - {channel_id("claude", session_id)}
    deadline = time.monotonic() + (5 if previous else 0)
    while wait_state.is_armed(lemon_id) and previous and time.monotonic() < deadline:
        time.sleep(0.1)
    if wait_state.is_armed(lemon_id):
        return True

    entry = session(session_id, wait)
    if why := problem(entry):
        _log.info("no push scout for %s: %s", lemon_id, why)
        return False

    assert entry is not None  # problem() names a missing session
    try:
        _spawn(entry)
    except OSError as error:
        _log.warning("could not start a push scout for %s: %s", lemon_id, error)
        return False

    if wait_state.is_armed(lemon_id, grace):
        return True

    _log.warning("push scout for %s did not start within %ss; see %s", lemon_id, grace, _log_path())
    return False


def start(session_id: str, lemon_id: str) -> int:
    """`watch --self --push`: the exit code, after saying what now runs."""
    if ensure(session_id, lemon_id):
        print("push scout running" if running(lemon_id) else "watcher running")
        return 0

    why = problem(session(session_id)) or f"the scout did not take its lock; see {_log_path()}"
    print(f"not started: {why}")
    return 2
