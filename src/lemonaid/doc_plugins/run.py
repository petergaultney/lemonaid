"""Asking a plugin about one snapshot of a document.

Each plugin runs once per lemonaid process and serves every call (plugins/running.py),
after saying hello as `lemonaid-doc-plugin 1`. A request is `<operation> <path>`, a
`name <name>` line per reader name, and the document as `text`; see docs/doc-plugins.md.
One that
fails is closed and started again on a later call, no sooner than `RETRY_AFTER`, so a
broken plugin isn't started on every poll. A result depends only on its inputs (see
docs/doc-plugins.md), so the latest result for each plugin, operation, document and reader
is kept with a digest of the text it answered: a waiter that reads an unchanged doc every
second asks nothing, and a document edited many times costs one answer, not one per
snapshot. A failure is never kept, and is reported on stderr.
"""

import atexit
import collections
import hashlib
import sys
import threading
import time
from collections import abc
from pathlib import Path

from ..plugins import running
from ..plugins.command import Plugin

HELLO = b"lemonaid-doc-plugin 1"
TIMEOUT = 10.0  # seconds for a plugin to start, or to answer one call
RETRY_AFTER = 10.0  # seconds after a failure before the plugin is started again
_KEEP = 256  # documents and readers, not snapshots

_Slot = tuple[Plugin, str, str, tuple[str, ...]]
_results: collections.OrderedDict[_Slot, tuple[str, str]] = collections.OrderedDict()
_running: dict[Plugin, running.Running] = {}
_failed_at: dict[Plugin, float] = {}
_locks: collections.defaultdict[Plugin, threading.Lock] = collections.defaultdict(threading.Lock)
_lock = threading.Lock()  # guards the four tables above


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _backing_off(plugin: Plugin) -> bool:
    return plugin not in _running and (
        time.monotonic() - _failed_at.get(plugin, -RETRY_AFTER) < RETRY_AFTER
    )


def _ask(plugin: Plugin, operation: str, path: Path, text: str, args: abc.Sequence[str]) -> str:
    """Under the plugin's own lock; raises running.Failed."""
    started = _running.get(plugin)
    if started is None:
        started = _running[plugin] = running.Running(plugin, HELLO, TIMEOUT)
    return started.ask(f"{operation} {path}", [("name", n) for n in args], text)


def _fail(plugin: Plugin, error: running.Failed) -> None:
    print(f"doc plugin {plugin.name}: {error}", file=sys.stderr, flush=True)
    _failed_at[plugin] = time.monotonic()
    if (started := _running.pop(plugin, None)) is not None:
        started.close()


def call(
    plugin: Plugin, operation: str, path: Path, text: str, args: abc.Sequence[str] = ()
) -> str | None:
    """*plugin*'s answer to *operation* on *text*, the document at *path*, or None if it failed
    now or failed within the last `RETRY_AFTER` seconds."""
    slot = (plugin, operation, str(path), tuple(args))
    digest = _digest(text)
    with _lock:
        if slot in _results:
            _results.move_to_end(slot)
            kept_digest, kept = _results[slot]
            if kept_digest == digest:
                return kept

        plugin_lock = _locks[plugin]
    with plugin_lock:
        if _backing_off(plugin):
            return None  # its failure was reported when it happened

        try:
            found = _ask(plugin, operation, path, text, args)
        except running.Failed as e:
            _fail(plugin, e)
            return None

    with _lock:
        _results[slot] = (digest, found)
        _results.move_to_end(slot)
        while len(_results) > _KEEP:
            _results.popitem(last=False)
    return found


def stop_all() -> None:
    """Close every running plugin; also run when the process exits."""
    for plugin in list(_running):
        with _locks[plugin]:
            if (started := _running.pop(plugin, None)) is not None:
                started.close()


atexit.register(stop_all)
