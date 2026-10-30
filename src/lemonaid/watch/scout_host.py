"""The scout host: one long-lived process that runs every lemon's push scout as a thread.

It runs a scout for each registration in `scout_roster`, and stops one when its
registration is removed or replaced. A scout that ends normally removes its own
registration; one that fails is tried again after `RETRY_SECONDS`. On `restart.SIGNAL`
it stops every scout and re-execs itself, and the registrations on disk bring them back
on the new code. It exits once it has had no registrations for `IDLE_SECONDS`.

It also runs the services its caller passes (`host_services`), such as tmux tab labels,
and stays up while any of them has work.
"""

import argparse
import dataclasses
import functools
import os
import sys
import threading
import time
from collections import abc

from ..log import get_logger
from . import (
    host_services,
    hosted_scout,
    kqueue_waits,
    registry,
    restart,
    scout_roster,
    waiter_lock,
    waits,
)

_log = get_logger("watch.scout_host")

RETRY_SECONDS = 30.0
IDLE_SECONDS = 60.0
_TICK = 0.5
_JOIN_SECONDS = 40.0  # longer than a scout takes to finish writing its delivered cursors

Run = abc.Callable[[scout_roster.Registration, abc.Callable[[], bool]], hosted_scout.Outcome]


@dataclasses.dataclass
class _Scout:
    registration: scout_roster.Registration
    stop: threading.Event
    thread: threading.Thread
    outcome: hosted_scout.Outcome = "stopped"


def _start(registration: scout_roster.Registration, run: Run, quitting: threading.Event) -> _Scout:
    stop = threading.Event()
    scout = _Scout(registration, stop, threading.Thread())

    def body() -> None:
        try:
            scout.outcome = run(registration, lambda: stop.is_set() or quitting.is_set())
        except Exception:  # the host outlives any one lemon's scout
            _log.exception("scout for %s crashed", registration.lemon_id)
            scout.outcome = "retry"

    scout.thread = threading.Thread(target=body, name=f"scout-{registration.lemon_id}", daemon=True)
    scout.thread.start()
    return scout


def _tick(
    scouts: dict[str, _Scout],
    retry_at: dict[str, float],
    run: Run,
    quitting: threading.Event,
) -> int:
    """Make the running scouts match the registrations; how many there are."""
    environment = scout_roster.environment()
    wanted = {
        lemon_id: r for lemon_id, r in scout_roster.listed().items() if r.environment == environment
    }
    for lemon_id, scout in list(scouts.items()):
        if wanted.get(lemon_id) != scout.registration:
            scout.stop.set()
        if scout.thread.is_alive():
            continue

        del scouts[lemon_id]
        if scout.outcome == "ended":
            scout_roster.remove(lemon_id, scout.registration.token)
            wanted.pop(lemon_id, None)
        elif scout.outcome == "retry":
            retry_at[scout.registration.token] = time.monotonic() + RETRY_SECONDS
    for lemon_id, registration in wanted.items():
        if lemon_id not in scouts and time.monotonic() >= retry_at.get(registration.token, 0):
            retry_at.pop(registration.token, None)
            scouts[lemon_id] = _start(registration, run, quitting)
    return len(wanted)


def _stop_all(scouts: dict[str, _Scout], quitting: threading.Event, pacing: waits.Waits) -> None:
    quitting.set()
    pacing.wake_all()
    deadline = time.monotonic() + _JOIN_SECONDS
    for scout in scouts.values():
        scout.thread.join(timeout=max(0, deadline - time.monotonic()))


def _pacing() -> waits.Waits:
    if not kqueue_waits.available():
        return waits.TIMERS

    kqueue_waits.raise_file_limit()
    return kqueue_waits.Hub()


def serve(
    run: Run | None = None,
    idle: float = IDLE_SECONDS,
    services: abc.Iterable[host_services.Factory] = (),
) -> int:
    """`lemonaid watch host`: 3 when another host already runs.

    Its scouts sleep on kqueue events where the platform has kqueue, and on timers elsewhere.
    """
    path = scout_roster.host_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = waiter_lock.acquire(path, grace=0)
    if lock is None:
        return 3

    pacing = _pacing() if run is None else waits.TIMERS
    run = run or functools.partial(hosted_scout.run, pacing=pacing)
    scouts: dict[str, _Scout] = {}
    retry_at: dict[str, float] = {}  # by registration token
    running = [start() for start in services]
    quitting = threading.Event()
    empty_since = time.monotonic()
    _log.info("scout host started: pid=%s", os.getpid())
    try:
        with (
            restart.listening(),
            registry.registered(
                "host",
                (),
                "",
                "lemonaid watch host",
                version=restart.version(),
                restartable=True,
                code=restart.fingerprint(),
            ),
        ):
            while not restart.requested():
                working = [_tick(scouts, retry_at, run, quitting), len(scouts)]
                working += [service.tick(quitting) for service in running]
                if any(working):
                    empty_since = time.monotonic()
                elif time.monotonic() - empty_since >= idle:
                    break
                time.sleep(_TICK)
    finally:
        _stop_all(scouts, quitting, pacing)
        for service in running:
            service.join()
        lock.close()
    if (
        restart.requested()
        or any(service.pending() for service in running)
        or any(r.environment == scout_roster.environment() for r in scout_roster.listed().values())
    ):
        _log.info("scout host restarting: pid=%s", os.getpid())
        restart.restart()  # a registration written while it was stopping needs a host
    _log.info("scout host exited: pid=%s", os.getpid())
    return 0


def add_parser(
    subparsers: argparse._SubParsersAction, services: abc.Sequence[host_services.Factory] = ()
) -> None:
    parser = subparsers.add_parser("host", help=argparse.SUPPRESS)
    parser.set_defaults(func=lambda a: sys.exit(serve(services=services)))
