"""The plugin processes this lemonaid process runs, of every kind: one per plugin, shared by
every caller, started on first use and closed at exit.

A plugin that fails is closed and started again on a later call, no sooner than
`RETRY_AFTER`, so a broken plugin isn't started on every poll. Its failure is printed once,
when it happens.
"""

import atexit
import collections
import dataclasses
import sys
import threading
import time
from collections import abc

from . import running
from .command import Plugin

RETRY_AFTER = 10.0
_NOTICES = 0.2  # seconds a notice reader holds a plugin between requests


@dataclasses.dataclass(frozen=True)
class Kind:
    hello: bytes
    timeout: float  # seconds for a plugin to start, or to answer one request
    label: str  # names the plugin in a printed failure, such as "doc plugin"
    refusal_fails: bool = False  # an `error` answer also closes the plugin
    on_notice: running.Notice | None = None  # notices are also read between requests
    on_retry: abc.Callable[["Launch"], object] | None = None  # `RETRY_AFTER` after a failure


@dataclasses.dataclass(frozen=True)
class Launch:
    kind: Kind
    plugin: Plugin
    env: tuple[tuple[str, str], ...] = ()  # added to lemonaid's own environment


_running: dict[Launch, running.Running] = {}
_failed_at: dict[Launch, float] = {}
_generation: collections.Counter[Launch] = collections.Counter()  # failures so far
_locks: collections.defaultdict[Launch, threading.Lock] = collections.defaultdict(threading.Lock)


def may_start(launch: Launch) -> bool:
    """Whether the plugin runs, or may be started again after its last failure."""
    return (
        launch in _running or time.monotonic() - _failed_at.get(launch, -RETRY_AFTER) >= RETRY_AFTER
    )


def generation(launch: Launch) -> int:
    """Changes each time the plugin fails, so a caller knows its next process is new."""
    return _generation[launch]


def _fail(launch: Launch, error: running.Failed) -> None:
    """Under the launch's lock."""
    print(f"{launch.kind.label} {launch.plugin.name}: {error}", file=sys.stderr, flush=True)
    _failed_at[launch] = time.monotonic()
    _generation[launch] += 1
    if (started := _running.pop(launch, None)) is not None:
        started.close()
    if launch.kind.on_retry:
        retry = threading.Timer(RETRY_AFTER, launch.kind.on_retry, (launch,))
        retry.daemon = True
        retry.start()


def _read_notices(launch: Launch, started: running.Running) -> None:
    while True:
        with _locks[launch]:
            if _running.get(launch) is not started:
                return

            try:
                started.read_notices(_NOTICES)
            except running.Failed as error:
                _fail(launch, error)
                return
        time.sleep(0.01)  # lets a waiting request take the lock


def _started(launch: Launch) -> running.Running:
    """Under the launch's lock; raises running.Failed."""
    if (found := _running.get(launch)) is not None:
        return found

    if not may_start(launch):
        raise running.Failed("failed recently; not started again yet")

    kind = launch.kind
    try:
        found = _running[launch] = running.Running(
            launch.plugin, kind.hello, kind.timeout, kind.on_notice, dict(launch.env)
        )
    except running.Failed as error:
        _fail(launch, error)
        raise
    if kind.on_notice:
        threading.Thread(
            target=_read_notices,
            args=(launch, found),
            name=f"plugin-{launch.plugin.name}",
            daemon=True,
        ).start()
    return found


def ask(launch: Launch, header: str, fields: abc.Sequence[tuple[str, str]], text: str) -> str:
    """The plugin's answer, or running.Failed with what went wrong (running.Refused for an
    `error` answer)."""
    with _locks[launch]:
        try:
            return _started(launch).ask(header, fields, text)
        except running.Refused as error:
            if launch.kind.refusal_fails:
                _fail(launch, error)
            raise
        except running.Failed as error:
            if launch in _running:
                _fail(launch, error)
            raise


def close() -> None:
    """Close every running plugin; also run when the process exits."""
    for launch in list(_running):
        with _locks[launch]:
            if (started := _running.pop(launch, None)) is not None:
                started.close()


atexit.register(close)
