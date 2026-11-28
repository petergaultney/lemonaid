"""An OpenClaw lemon's scout: `lemonaid watch --self --push`, in the scout host, while its session lasts.

Each batch becomes one agent turn in the session through the gateway, so the lemon wakes
for its mail and events the way a Codex lemon does through `codex queue`. No batch goes while
the session is mid-turn, so a busy lemon gets one turn for everything that arrived meanwhile,
not a queue of them. A body change it made doesn't wake it: lemonaid's OpenClaw plugin records
each tool call's edits, as Claude's and Codex's hooks do, and without the plugin any change
seen during its turn counts as its own.
"""

import time
import typing as ty
from collections import abc
from pathlib import Path

from ..inbox import db
from ..log import LOG_PATH, get_logger
from ..openclaw import plugin_install, run_records, sessions
from . import (
    batch_text,
    deaf_waiter,
    delivery,
    push_scout,
    scout_roster,
    scout_start,
    turns,
    wait_state,
    waiter_lock,
)

_log = get_logger("watch.openclaw_scout")

_NEXT = "delivers the next batch as another turn in this session"
_ACCEPT_TIMEOUT_MS = 60_000
_LIST_EVERY = 60.0  # seconds between the scout's checks that its session still exists


def _recording_sends(send: delivery.Deliver, session_key: str) -> delivery.Deliver:
    """*send*, recording the session as mid-turn once the gateway accepts the turn, before
    anything that reports turns has seen it start."""

    def sending(message: str) -> None:
        at = time.time()
        send(message)
        with db.connect() as conn:
            run_records.sent(conn, session_key, at)

    return sending


class Harness(ty.NamedTuple):
    deliver: delivery.Deliver
    alive: abc.Callable[[], bool]
    writer: str
    latest_turn: turns.Turns
    edits_by_turn: bool  # no plugin records own edits per tool call, so a turn's changes count


def harness(channel: str) -> Harness:
    """How the scout of the lemon on *channel* reaches its session and tells when it is busy."""
    key = sessions.session_key(channel)
    exists = sessions.exists_checker(sessions.cli(), _LIST_EVERY)
    send = delivery.openclaw_turn(  # waiting out the turn would stall the scout's heartbeat
        key,
        sessions.cli(),
        _ACCEPT_TIMEOUT_MS,
        lambda m: batch_text.compose(m, _NEXT),
        until_final=False,
    )
    return Harness(
        _recording_sends(send, key),
        lambda: exists(key) is not False,
        f"openclaw-{key}",
        sessions.recorded_turns(key),
        not plugin_install.installed(),
    )


def _serves(lemon_id: str, channel: str) -> bool:
    """Whether the lemon's armed watcher, if a scout, serves *channel* rather than a session its
    brief has left. A watcher with no registration is the lemon's own, run in the session."""
    registration = scout_roster.read(lemon_id)
    return registration is None or registration.channel == channel


def ensure(channel: str, lemon_id: str, cwd: str) -> bool:
    """Whether a scout runs for the lemon, starting one in the scout host if none does."""
    deaf_waiter.clear(lemon_id, channel)
    if wait_state.is_armed(lemon_id) and _serves(lemon_id, channel):
        return True

    path = wait_state.lock_path(lemon_id).with_suffix(".start.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = waiter_lock.acquire(path, grace=0)
    if lock is None:
        return False

    try:
        if not (wait_state.is_armed(lemon_id) and _serves(lemon_id, channel)):
            scout_start.host(
                lemon_id, channel, "", cwd or str(Path.home())
            )  # replaces another session's
            _log.info("starting OpenClaw push scout channel=%s", channel)
        return wait_state.is_armed(lemon_id, grace=10) and _serves(lemon_id, channel)
    except OSError as error:
        _log.warning("could not start a push scout for %s: %s", channel, error)
        return False
    finally:
        lock.close()


def start(channel: str, lemon_id: str, cwd: str) -> int:
    """`watch --self --push`: the exit code, after saying what now runs."""
    if ensure(channel, lemon_id, cwd):
        print("push scout running" if push_scout.running(lemon_id) else "watcher running")
        return 0

    print(f"not started: the scout did not take its lock; see {LOG_PATH}")
    return 2
