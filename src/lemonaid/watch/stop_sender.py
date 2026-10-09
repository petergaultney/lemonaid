"""Who asked lemonaid to stop a waiter, kept beside its registry entry for the waiter to read.

A signal handler can't learn the sending pid, so `watch stop` writes this note before
it signals. A waiter that gets SIGTERM with no note was stopped by something outside
lemonaid: a `kill`, a `pkill` pattern or its harness.
"""

import json
import os
import pathlib


def _path(entry: pathlib.Path) -> pathlib.Path:
    return entry.with_suffix(".stop")


def record(entry: pathlib.Path, channel: str) -> None:
    _path(entry).write_text(json.dumps({"pid": os.getpid(), "channel": channel}))


def clear(entry: pathlib.Path) -> None:
    _path(entry).unlink(missing_ok=True)


def describe(entry: pathlib.Path) -> str:
    """Who stopped the waiter whose registry entry is `entry`."""
    try:
        note = json.loads(_path(entry).read_text())
        return f"`lemonaid watch stop`, run by {note['channel'] or 'an unknown lemon'} (pid {note['pid']})"
    except (OSError, ValueError, TypeError, KeyError):
        return "a process outside lemonaid (a kill or pkill, or the harness)"
