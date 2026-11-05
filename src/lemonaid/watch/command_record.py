"""What `lemonaid run` writes about the command it runs, and how a process is told apart from
a later one that reuses its pid.

A record lives at `<state>/commands/<pid>.json`, where the pid is the `lemonaid run` wrapper's.
The wrapper writes the exit status into it before it exits itself, so once the wrapper's pid is
gone the record is final. A record still without an exit means the wrapper was killed outright.
"""

import dataclasses
import json
import os
import pathlib
import subprocess
import time

from . import cursors

_PRUNE_AFTER = 7 * 24 * 3600.0


@dataclasses.dataclass(frozen=True)
class Record:
    pid: int
    started: str  # the wrapper's start time, as `process_start` gives it
    command: str
    cwd: str
    lemon: str
    began: float  # time.time() when the wrapper started
    exit: int | None = None  # the command's exit status; a signal is 128 + its number
    signal: str = ""  # the signal's name, when one ended the command
    ended: float = 0.0


def directory() -> pathlib.Path:
    return cursors.root().parent / "commands"


def _path(pid: int) -> pathlib.Path:
    return directory() / f"{pid}.json"


def process_start(pid: int) -> str:
    """When process *pid* started, as `ps` prints it, or "" when none runs; an exited
    process its parent has not reaped yet (a zombie) does not run."""
    if pid <= 0:
        return ""

    try:
        found = subprocess.run(
            ["ps", "-o", "stat=,lstart=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "" if not _exists(pid) else "?"
    state, _, started = found.stdout.strip().partition(" ")
    return "" if state.startswith("Z") else " ".join(started.split())


def _exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read(pid: int) -> Record | None:
    try:
        saved = json.loads(_path(pid).read_text())
        return Record(**saved)
    except (OSError, ValueError, TypeError):
        return None


def write(record: Record) -> None:
    cursors.write_json(_path(record.pid), dataclasses.asdict(record))


def prune(now: float) -> None:
    """Remove records of commands that ended (or began) over a week ago."""
    for path in directory().glob("*.json"):
        try:
            if now - path.stat().st_mtime > _PRUNE_AFTER:
                path.unlink()
        except OSError:
            pass


def begin(command: str, cwd: str, lemon: str) -> Record:
    pid = os.getpid()
    record = Record(pid, process_start(pid), command, cwd, lemon, time.time())
    prune(record.began)
    write(record)
    return record
