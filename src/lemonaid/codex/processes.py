"""Which Codex processes run which threads, from what Codex's hooks recorded.

Each hook records the Codex process it runs under (`launch/restart/native.py`). A recorded
process still runs when `ps` shows the same pid started at the same moment. When one
process has run several threads, as after `/clear`, the thread it reported last is the one
it runs. A process under the shared app-server daemon serves every terminal at once, so it
names none of them.
"""

import json
import os
import subprocess
import time
import typing as ty
from pathlib import Path

from ..launch.restart import process, state
from ..log import get_logger

_log = get_logger("codex.processes")
_TIMEOUT = 1


class Running(ty.NamedTuple):
    thread: str
    tty: str  # "" under the shared daemon
    executable: str


class _Live(ty.NamedTuple):
    started: str  # as `ps` writes it
    tty: str
    argv: list[str]


def _live() -> dict[int, _Live] | None:
    """Every running Codex process by pid; None if `ps` fails."""
    try:
        result = subprocess.run(
            ["ps", "-A", "-ww", "-o", "pid=,stat=,tty=,lstart=,args="],  # -ww: whole args
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as error:
        _log.debug("could not list Codex processes: %s", error)
        return None

    if result.returncode:
        return None

    live = {}
    for fields in (line.split() for line in result.stdout.splitlines()):
        if len(fields) < 9 or fields[1].startswith("Z") or Path(fields[8]).name != "codex":
            continue
        live[int(fields[0])] = _Live(" ".join(fields[3:8]), fields[2], fields[8:])
    return live


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


def running() -> list[Running] | None:
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
                result.append(Running(thread, "" if daemon else found.tty, executable))
    return result


def open_threads() -> set[str] | None:
    """Threads a live Codex process runs, the shared daemon included."""
    found = running()
    return None if found is None else {each.thread for each in found}


def thread_ttys() -> dict[str, set[str]] | None:
    """The terminal each thread's Codex process runs in; the shared daemon names none."""
    found = running()
    if found is None:
        return None

    ttys: dict[str, set[str]] = {}
    for each in found:
        if each.tty and each.tty not in ("?", "??"):
            ttys.setdefault(each.thread, set()).add(f"/dev/{each.tty.removeprefix('/dev/')}")
    return ttys


def executable(thread: str) -> str:
    """The executable of the Codex process running *thread*, or "".

    Running `codex queue` with it works even where `codex` on PATH does not.
    """
    return next(
        (
            each.executable
            for each in running() or []
            if each.thread == thread and os.path.isabs(each.executable)
        ),
        "",
    )
