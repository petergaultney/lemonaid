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


def record(
    entry: pathlib.Path, channel: str, command: str = "lemonaid watch stop", followed: bool = False
) -> None:
    """*followed*: the lemon's watcher follows what the waiter watched, so it needs no rearm."""
    _path(entry).write_text(
        json.dumps(
            {"pid": os.getpid(), "channel": channel, "command": command, "followed": followed}
        )
    )


def clear(entry: pathlib.Path) -> None:
    _path(entry).unlink(missing_ok=True)


def requested(entry: pathlib.Path) -> bool:
    """Whether `watch stop` asked for this stop, so it is a normal exit."""
    return _path(entry).is_file()


def _note(entry: pathlib.Path) -> dict:
    try:
        note = json.loads(_path(entry).read_text())
    except (OSError, ValueError):
        return {}
    return note if isinstance(note, dict) else {}


def describe(entry: pathlib.Path) -> str:
    """Who stopped the waiter whose registry entry is `entry`."""
    note = _note(entry)
    if "pid" not in note:
        return "a process outside lemonaid (a kill or pkill, or the harness)"

    by = f", run by {note['channel']}" if note.get("channel") else ""
    return f"`{note.get('command', 'lemonaid watch stop')}`{by} (pid {note['pid']})"


def followed(entry: pathlib.Path) -> bool:
    return _note(entry).get("followed") is True
