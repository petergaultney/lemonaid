"""The watch sources this lemonaid process runs: one plugin process per source, shared by every
subscription in the process, started on first use and closed at exit.

Each says hello as `lemonaid-source-plugin 1` and is asked `check`, `poll <id>` and
`forget <id>` (docs/source-plugins.md). Between requests a thread reads its notices, so a
`ready <id>` reaches the subscription it names at once. One that fails is closed and started
again on a later call, no sooner than `RETRY_AFTER`.
"""

import atexit
import collections
import functools
import os
import shlex
import sys
import threading
import time
from collections import abc
from pathlib import Path

from ..plugins import running
from .plugin import Source

HELLO = b"lemonaid-source-plugin 1"
TIMEOUT = 60.0  # seconds for a plugin to start, or to answer one call; a poll may page Slack
RETRY_AFTER = 10.0
_NOTICES = 0.2  # seconds a notice reader holds a plugin between requests


class Failed(Exception):
    pass


class Refused(Failed):
    """The plugin runs, but answered `error`: a usage message for `check`."""


class _Host:
    def __init__(self) -> None:
        self.running: dict[Source, running.Running] = {}
        self.failed_at: dict[Source, float] = {}
        self.locks: collections.defaultdict[Source, threading.Lock] = collections.defaultdict(
            threading.Lock
        )
        self.ready: set[str] = set()  # subscription ids a plugin said are ready to poll
        # each subscription's source, and the event that wakes its scout
        self.listening: dict[str, tuple[Source, threading.Event]] = {}
        self.generation: collections.Counter[Source] = collections.Counter()  # failures so far
        self.lock = threading.Lock()  # guards ready and listening


_host = _Host()


def _state_root() -> Path:
    return Path(os.environ.get("LEMONAID_STATE_DIR") or "~/.local/state/lemonaid").expanduser()


def env(source: Source) -> dict[str, str]:
    """What a plugin is started with: a state directory of its own, its config table, and the
    command that runs this lemonaid."""
    return {
        "LEMONAID_PLUGIN_STATE": str(_state_root() / source.name),
        "LEMONAID_PLUGIN_CONFIG": source.table,
        "LEMONAID": shlex.join([sys.executable, "-m", "lemonaid"]),
    }


def _notice(line: str) -> None:
    verb, _, key = line.partition(" ")
    if verb == "ready" and key:
        with _host.lock:
            _host.ready.add(key)
            if found := _host.listening.get(key):
                found[1].set()


def _wake_all(source: Source) -> None:
    """Wake every scout following *source*, so each polls a process that knows its id."""
    with _host.lock:
        events = [event for s, event in _host.listening.values() if s == source]
    for event in events:
        event.set()


def _read_notices(source: Source, started: running.Running) -> None:
    while True:
        with _host.locks[source]:
            if _host.running.get(source) is not started:
                return

            try:
                started.read_notices(_NOTICES)
            except running.Failed as error:
                _fail(source, error)
                return
        time.sleep(0.01)  # lets a waiting request take the lock


def may_start(source: Source) -> bool:
    """Whether *source*'s plugin runs, or may be started again after its last failure."""
    return (
        source in _host.running
        or time.monotonic() - _host.failed_at.get(source, -RETRY_AFTER) >= RETRY_AFTER
    )


def _started(source: Source) -> running.Running:
    """Under the source's lock; raises running.Failed."""
    if (found := _host.running.get(source)) is not None:
        return found

    if not may_start(source):
        raise running.Failed("failed recently; not started again yet")

    try:
        found = _host.running[source] = running.Running(
            source.plugin, HELLO, TIMEOUT, _notice, env(source)
        )
    except running.Failed as error:
        _fail(source, error)
        raise
    threading.Thread(
        target=_read_notices, args=(source, found), name=f"source-{source.name}", daemon=True
    ).start()
    return found


def _fail(source: Source, error: running.Failed) -> None:
    """Under the source's lock. Its subscriptions poll again once it may be started again."""
    print(f"watch source {source.name}: {error}", file=sys.stderr, flush=True)
    _host.failed_at[source] = time.monotonic()
    _host.generation[source] += 1
    if (started := _host.running.pop(source, None)) is not None:
        started.close()
    retry = threading.Timer(RETRY_AFTER, _wake_all, (source,))
    retry.daemon = True
    retry.start()


def ask(source: Source, header: str, fields: abc.Sequence[tuple[str, str]], text: str) -> str:
    """The plugin's answer, or Failed with what went wrong."""
    with _host.locks[source]:
        try:
            return _started(source).ask(header, fields, text)
        except running.Refused as error:
            raise Refused(str(error)) from error
        except running.Failed as error:
            if source in _host.running:
                _fail(source, error)
            raise Failed(str(error)) from error


def generation(source: Source) -> int:
    """Changes each time *source*'s plugin fails, so a subscription knows to poll its next
    process, which has never heard of it."""
    return _host.generation[source]


def listen(key: str, source: Source, wake: threading.Event) -> None:
    """Set *wake* when subscription *key* is ready, or its plugin failed."""
    with _host.lock:
        _host.listening[key] = (source, wake)


def unlisten(key: str) -> None:
    with _host.lock:
        _host.listening.pop(key, None)
        _host.ready.discard(key)


def take_ready(key: str) -> bool:
    """Whether the plugin said subscription *key* is ready since the last look."""
    with _host.lock:
        if key in _host.ready:
            _host.ready.discard(key)
            return True

    return False


@functools.lru_cache(maxsize=256)
def check(source: Source, args: tuple[str, ...]) -> tuple[str, ...]:
    """What `lemonaid watch <source> <args>` follows, as the plugin names it, or Failed with
    the plugin's usage message."""
    answer = ask(source, "check", [("arg", a) for a in args], "")
    return tuple(
        line.removeprefix("target ") for line in answer.splitlines() if line.startswith("target ")
    )


def close() -> None:
    for source in list(_host.running):
        with _host.locks[source]:
            if (started := _host.running.pop(source, None)) is not None:
                started.close()


atexit.register(close)
