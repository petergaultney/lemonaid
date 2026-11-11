"""Exit detection for one watched process, independent of how the event is delivered.

The cursor holds the process's start time as first seen, so a later process that reuses the
pid counts as the watched one having exited, and whether the exit was already reported, so a
rearm stays quiet. A process `lemonaid run` started has a record (see command_record.py) that
gives its command and exit status; any other process is reported with its status unknown.
"""

import dataclasses
import json
import pathlib
import time
import typing as ty

from ..log import get_logger
from . import command_record, cursors, delivery

_log = get_logger("watch.command_events")


@dataclasses.dataclass
class CommandWatch:
    pid: int
    cursor: pathlib.Path
    started: str  # "" when nothing ran under the pid when first watched
    reported: bool


def state_stem(state_dir: pathlib.Path, pid: int, me: str) -> pathlib.Path:
    return state_dir / (f"{pid}-{me}" if me else str(pid))


def _generation(pid: int) -> str:
    """The process a new watch on *pid* means: the one running now, else the last recorded one."""
    if live := command_record.process_start(pid):
        return live

    record = command_record.read(pid)
    return record.started if record else ""


def _saved(cursor: pathlib.Path) -> CommandWatch | None:
    try:
        saved = json.loads(cursor.read_text())
        return CommandWatch(0, cursor, saved["started"], saved["reported"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def open_watch(state_dir: pathlib.Path, pid: int, me: str) -> CommandWatch:
    """A rearm keeps the process it first watched, until that process's exit is reported;
    after that, a different process under the pid is a new watch."""
    state_dir.mkdir(parents=True, exist_ok=True)
    cursor = state_stem(state_dir, pid, me).with_suffix(".json")
    generation = _generation(pid)
    saved = _saved(cursor)
    if saved and (not saved.reported or generation in ("", saved.started)):
        return CommandWatch(pid, cursor, saved.started, saved.reported)

    watch = CommandWatch(pid, cursor, generation, False)
    cursors.write_json(cursor, {"started": watch.started, "reported": False})
    _log.info("watching pid %s, started %r", pid, watch.started)
    return watch


def _duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    if minutes < 1:
        return f"{seconds:.0f}s"

    return f"{minutes}m" if minutes < 120 else f"{minutes / 60:.1f}h"


def _message(w: CommandWatch, record: command_record.Record | None) -> str:
    if record is None or (w.started and record.started != w.started):
        if not w.started:
            return f"process {w.pid} is not running, and was not running when this watch started; its exit status is unknown"

        return f"process {w.pid} exited; its exit status is unknown (it was not started with `lemonaid run`)"

    what = f"`{record.command}` (pid {w.pid}, in {record.cwd})"
    if record.exit is None:
        return f"{what} ended without recording its exit status: its `lemonaid run` was killed, or the machine restarted"

    took = _duration(record.ended - record.began)
    if record.signal:
        return f"{what} was ended by {record.signal} (exit {record.exit}) after {took}"

    return f"{what} exited with status {record.exit} after {took}"


def message_if_exited(w: CommandWatch) -> str:
    """The exit to report, or "" while the watched process still runs or was already reported."""
    if w.reported:
        return ""

    record = command_record.read(w.pid)
    if record and record.started == w.started and record.exit is not None:
        return _message(w, record)

    live = command_record.process_start(w.pid)
    if live and w.started and (live == w.started or "?" in (live, w.started)):
        return ""

    return _message(w, record)


def poll(w: CommandWatch, deliver: ty.Callable[[str], object]) -> bool:
    """Deliver the exit once; True if it was delivered now. State advances only after `deliver`."""
    message = message_if_exited(w)
    if not message:
        return False

    deliver(delivery.Labeled(message, f"pid {w.pid} exited"))
    w.reported = True
    cursors.write_json(w.cursor, {"started": w.started, "reported": True, "at": time.time()})
    _log.info("reported pid %s: %s", w.pid, message)
    return True
