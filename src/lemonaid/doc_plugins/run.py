"""Asking a plugin about one snapshot of a document.

Each plugin runs once per lemonaid process and serves every call (plugins/processes.py),
after saying hello as `lemonaid-doc-plugin 1`. A request is `<operation> <path>`, a
`name <name>` line per reader name, and the document as `text`; see docs/doc-plugins.md.
A result depends only on its inputs (see docs/doc-plugins.md), so the latest result for each
plugin, operation, document and reader is kept with a digest of the text it answered: a
waiter that reads an unchanged doc every second asks nothing, and a document edited many
times costs one answer, not one per snapshot. A failure is never kept.
"""

import collections
import hashlib
import threading
from collections import abc
from pathlib import Path

from ..plugins import processes, running
from ..plugins.command import Plugin

HELLO = b"lemonaid-doc-plugin 1"
TIMEOUT = 10.0  # seconds for a plugin to start, or to answer one call
_KEEP = 256  # documents and readers, not snapshots
_KIND = processes.Kind(HELLO, TIMEOUT, "doc plugin", refusal_fails=True)

_Slot = tuple[Plugin, str, str, tuple[str, ...]]
_results: collections.OrderedDict[_Slot, tuple[str, str]] = collections.OrderedDict()
_lock = threading.Lock()  # guards _results


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def call(
    plugin: Plugin, operation: str, path: Path, text: str, args: abc.Sequence[str] = ()
) -> str | None:
    """*plugin*'s answer to *operation* on *text*, the document at *path*, or None if it failed
    now or failed within the last `processes.RETRY_AFTER` seconds."""
    slot = (plugin, operation, str(path), tuple(args))
    digest = _digest(text)
    with _lock:
        if slot in _results:
            _results.move_to_end(slot)
            kept_digest, kept = _results[slot]
            if kept_digest == digest:
                return kept

    try:
        found = processes.ask(
            processes.Launch(_KIND, plugin),
            f"{operation} {path}",
            [("name", n) for n in args],
            text,
        )
    except running.Failed:
        return None  # printed when it happened

    with _lock:
        _results[slot] = (digest, found)
        _results.move_to_end(slot)
        while len(_results) > _KEEP:
            _results.popitem(last=False)
    return found
