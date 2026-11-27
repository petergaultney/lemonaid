"""Asking a watch source's plugin, which runs once per lemonaid process (plugins/processes.py).

Each says hello as `lemonaid-source-plugin 1` and is asked `check`, `poll <id>` and
`forget <id>` (docs/source-plugins.md). Between requests a thread reads its notices, so a
`ready <id>` reaches the subscription it names at once. When a plugin fails, every
subscription that follows it is woken once it may be started again.
"""

import functools
import os
import shlex
import sys
import threading
from pathlib import Path

from ..plugins import processes
from .plugin import Source

HELLO = b"lemonaid-source-plugin 1"
TIMEOUT = 60.0  # seconds for a plugin to start, or to answer one call; a poll may page Slack

_ready: set[str] = set()  # subscription ids a plugin said are ready to poll
# each subscription's plugin, and the event that wakes its scout
_listening: dict[str, tuple[processes.Launch, threading.Event]] = {}
_lock = threading.Lock()  # guards the two above


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
        with _lock:
            _ready.add(key)
            if found := _listening.get(key):
                found[1].set()


def _wake_all(launch: processes.Launch) -> None:
    """Wake every scout following *launch*, so each polls a process that knows its id."""
    with _lock:
        events = [event for followed, event in _listening.values() if followed == launch]
    for event in events:
        event.set()


_KIND = processes.Kind(HELLO, TIMEOUT, "watch source", on_notice=_notice, on_retry=_wake_all)


def launch(source: Source) -> processes.Launch:
    return processes.Launch(_KIND, source.plugin, tuple(env(source).items()))


def listen(key: str, launched: processes.Launch, wake: threading.Event) -> None:
    """Set *wake* when subscription *key* is ready, or its plugin failed."""
    with _lock:
        _listening[key] = (launched, wake)


def unlisten(key: str) -> None:
    with _lock:
        _listening.pop(key, None)
        _ready.discard(key)


def take_ready(key: str) -> bool:
    """Whether the plugin said subscription *key* is ready since the last look."""
    with _lock:
        if key in _ready:
            _ready.discard(key)
            return True

    return False


@functools.lru_cache(maxsize=256)
def check(source: Source, args: tuple[str, ...]) -> tuple[str, ...]:
    """What `lemonaid watch <source> <args>` follows, as the plugin names it, or
    running.Refused with the plugin's usage message."""
    answer = processes.ask(launch(source), "check", [("arg", a) for a in args], "")
    return tuple(
        line.removeprefix("target ") for line in answer.splitlines() if line.startswith("target ")
    )
