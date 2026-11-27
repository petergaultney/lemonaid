"""An OpenClaw lemon's scout: `lemonaid watch --self --push`, in the scout host, while its session lasts.

Each batch becomes one agent turn in the session through the gateway, so the lemon wakes
for its mail and events the way a Codex lemon does through `codex queue`. No batch goes while
the session is mid-turn, so a busy lemon gets one turn for everything that arrived meanwhile,
not a queue of them, and a body change it made during its turn doesn't wake it.
"""

import threading
import time
import typing as ty
from collections import abc
from pathlib import Path

from ..log import LOG_PATH, get_logger
from ..openclaw import sessions
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
_SENT_RUNS_FOR = 5.0  # seconds a sent turn counts as running, before the observer records it


def _sent_counts_as_running(
    send: delivery.Deliver, latest: turns.Turns, within: float
) -> tuple[delivery.Deliver, turns.Turns]:
    """*send* and *latest*, with the session counted as mid-turn for *within* seconds after a
    send, until the observer's record of the turn can say so itself."""
    sent = float("-inf")
    lock = threading.Lock()

    def sending(message: str) -> None:
        nonlocal sent
        send(message)
        with lock:
            sent = time.monotonic()

    def latest_turn() -> turns.Turn | None:
        with lock:
            recent = time.monotonic() - sent < within
        turn = latest()
        if not recent:
            return turn

        return turns.Turn(True, turn.started if turn else 0, turn.ended if turn else 0)

    return sending, latest_turn


class Harness(ty.NamedTuple):
    deliver: delivery.Deliver
    alive: abc.Callable[[], bool]
    writer: str
    latest_turn: turns.Turns


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
    deliver, latest_turn = _sent_counts_as_running(
        send, sessions.recorded_turns(key), _SENT_RUNS_FOR
    )
    return Harness(deliver, lambda: exists(key) is not False, f"openclaw-{key}", latest_turn)


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
