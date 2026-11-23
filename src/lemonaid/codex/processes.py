"""Which Codex processes run which threads, from what Codex's hooks recorded.

Each hook records the Codex process it runs under (`launch/restart/native.py`). A recorded
process still runs when `ps` shows the same pid started at the same moment. When one
process has run several threads, as after `/clear`, the thread it reported last is the one
it runs. A process under the shared app-server daemon serves every terminal at once, so it
names none of them.

A caller that polls, such as each of the scout host's Codex scouts, which all check their
threads at once, may pass a *max_age* to share one answer with the other callers in its
process. A caller about to act on where a lemon runs lists afresh.
"""

import json
import os
import subprocess
import threading
import time
import typing as ty
from pathlib import Path

from .. import process_table
from ..launch.restart import process, state
from ..log import get_logger

_log = get_logger("codex.processes")
_TIMEOUT = 1


class Running(ty.NamedTuple):
    thread: str
    tty: str  # "" under the shared daemon
    executable: str
    pid: int
    started: str  # as `ps` writes it


class _Live(ty.NamedTuple):
    started: str  # as `ps` writes it
    tty: str
    argv: list[str]


class _Answer(ty.NamedTuple):
    at: float  # monotonic, when its listing started
    running: list[Running] | None
    count: int  # shared answers so far, this one included


_answer_lock = threading.Lock()
_latest = _Answer(float("-inf"), None, 0)


def _live() -> dict[int, _Live] | None:
    """Every running Codex process by pid; None if `ps` fails or can't run here."""
    if process_table.sandboxed():
        return None

    try:
        found = process_table.listing("pid", "stat", "tty", "lstart", "args", timeout=_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as error:
        _log.debug("could not list Codex processes: %s", error)
        return None

    return {
        int(pid): _Live(started, tty, args.split())
        for pid, stat, tty, started, args in found
        if not stat.startswith("Z") and Path(args.split()[0]).name == "codex"
    }


def _resumed(argv: list[str]) -> str:
    """The thread a `codex resume <thread>` command line names, or ""."""
    return next((argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg == "resume"), "")


def _recorded(since: float) -> list[tuple[float, str, process.Identity]]:
    """(when, thread, process) for every Codex process a hook recorded since *since*."""
    found = []
    try:
        entries = list(os.scandir(state.root()))
    except FileNotFoundError:
        return found

    for entry in entries:
        try:
            if not entry.name.startswith("native-") or (when := entry.stat().st_mtime) < since:
                continue

            binding = json.loads(Path(entry.path).read_text())
            identity = process.Identity(**binding["identity"])
        except (OSError, ValueError, KeyError, TypeError):
            continue

        if Path(identity.executable).name == "codex" and isinstance(binding.get("session_id"), str):
            found.append((when, binding["session_id"], identity))
    return found


def _epoch(started: str) -> float:
    try:
        return time.mktime(time.strptime(started, "%a %b %d %H:%M:%S %Y"))
    except ValueError:
        return 0.0


def _running() -> list[Running] | None:
    """Every thread a live Codex process runs; None if the processes couldn't be listed.

    A terminal's process runs the thread it reported last, and the shared daemon every
    thread it reported. A process no hook has reported yet, such as one restore resumed
    that hasn't had a turn, runs the thread its `resume` argument names.
    """
    live = _live()
    if live is None:
        return None

    # A record written before the oldest of them started can't be about any of them.
    recorded = sorted(_recorded(min((_epoch(f.started) for f in live.values()), default=0.0)))
    reported: dict[int, list[tuple[str, str]]] = {}  # pid: [(thread, executable)], oldest first
    for _, thread, identity in recorded:
        found = live.get(identity.pid)
        if found is not None and found.started == identity.started:
            reported.setdefault(identity.pid, []).append((thread, identity.executable))

    result = []
    for pid, found in live.items():
        daemon = "app-server" in found.argv
        threads = reported.get(pid) or [(_resumed(found.argv), found.argv[0])]
        for thread, executable in threads if daemon else threads[-1:]:
            if thread:
                result.append(
                    Running(thread, "" if daemon else found.tty, executable, pid, found.started)
                )
    return result


def running(max_age: float = 0.0) -> list[Running] | None:
    """`_running`, or with *max_age*, an answer shared with other callers in this process:
    one under *max_age* seconds old, or the one another caller was getting while this one
    waited, however long that took.
    """
    global _latest
    if not max_age:
        return _running()

    seen = _latest.count
    with _answer_lock:
        if _latest.count == seen and time.monotonic() - _latest.at >= max_age:
            _latest = _Answer(time.monotonic(), _running(), seen + 1)
        return _latest.running


def owner(thread: str, max_age: float = 0.0) -> Running | None:
    """The process running *thread*; None when none does or the processes couldn't be listed."""
    return next((each for each in running(max_age) or [] if each.thread == thread), None)


def switched(found: Running) -> bool:
    """Whether the terminal process *found* has since reported another thread, as `/clear`
    makes it, from what its hooks recorded; it runs no `ps`."""
    if not found.tty:  # the shared daemon runs every thread it reported
        return False

    reported = [
        (when, thread)
        for when, thread, identity in _recorded(_epoch(found.started))
        if (identity.pid, identity.started) == (found.pid, found.started)
    ]
    return bool(reported) and max(reported)[1] != found.thread


def open_threads(max_age: float = 0.0) -> set[str] | None:
    """Threads a live Codex process runs, the shared daemon included."""
    found = running(max_age)
    return None if found is None else {each.thread for each in found}


def thread_ttys(max_age: float = 0.0) -> dict[str, set[str]] | None:
    """The terminal each thread's Codex process runs in; the shared daemon names none."""
    found = running(max_age)
    if found is None:
        return None

    ttys: dict[str, set[str]] = {}
    for each in found:
        if each.tty and each.tty not in ("?", "??"):
            ttys.setdefault(each.thread, set()).add(f"/dev/{each.tty.removeprefix('/dev/')}")
    return ttys


def executable(thread: str, max_age: float = 0.0) -> str:
    """The executable of the Codex process running *thread*, or "".

    Running `codex queue` with it works even where `codex` on PATH does not.
    """
    return next(
        (
            each.executable
            for each in running(max_age) or []
            if each.thread == thread and os.path.isabs(each.executable)
        ),
        "",
    )
