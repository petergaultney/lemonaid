"""Telling whether a Codex session with no tty is still running.

A Codex TUI can run its sessions on a shared `codex app-server` daemon, whose
notify hook has no terminal of the session's own, so its rows record no tty and
every tty-keyed liveness check passes them over. A Codex session's cwd is the
directory its TUI was started in, and the TUI keeps it as its working directory,
so with no Codex process working in that directory the session is gone.

This asks the machine's process table rather than tmux: the hook's `TMUX` is the
daemon's, so it cannot say which tmux server the session's pane is on. It is
Codex only: a Claude hook reports the cwd its shell has moved to.
"""

import os
import subprocess
from collections import abc

from ..log import get_logger

_log = get_logger("watcher.untracked")

_LSOF_TIMEOUT_SECONDS = 2

Row = tuple[str, str, str, float, bool, str | None, str, str | None]


def is_untracked(row: Row) -> bool:
    channel, _sid, cwd, _created, _unread, tty, _msg, source = row
    return channel.startswith("codex:") and not tty and source == "tmux" and bool(cwd)


def _subcommand(args: list[str]) -> str:
    """The first positional argument after the program, skipping `-c key=value` pairs."""
    rest = iter(args[1:])
    for arg in rest:
        if arg == "-c":
            next(rest, None)
        elif not arg.startswith("-"):
            return arg

    return ""


def is_app_server(args: list[str]) -> bool:
    """Whether a command line is `codex [-c k=v ...] app-server ...`."""
    return bool(args) and os.path.basename(args[0]) == "codex" and _subcommand(args) == "app-server"


def _app_server_pids(pids: abc.Collection[str]) -> set[str] | None:
    """Which of *pids* are the app-server or its helpers, whose cwd is its first TUI's."""
    if not pids:
        return set()

    try:
        result = subprocess.run(
            ["ps", "-o", "pid=,ppid=,args=", "-p", ",".join(pids)],
            capture_output=True,
            text=True,
            timeout=_LSOF_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _log.warning("could not read Codex command lines: %s", e)
        return None

    # ps exits 1 when some pid has exited since lsof saw it; the rest still print.
    processes = [
        (fields[0], fields[1], fields[2].split())
        for fields in (line.split(maxsplit=2) for line in result.stdout.splitlines())
        if len(fields) == 3
    ]
    servers = {pid for pid, _, args in processes if is_app_server(args)}
    return servers | {pid for pid, ppid, _ in processes if ppid in servers}


def codex_directories() -> set[str] | None:
    """Where every running Codex TUI works, or None if the process table couldn't be read."""
    try:
        result = subprocess.run(
            ["lsof", "-a", "-d", "cwd", "-c", "codex", "-Fpn"],
            capture_output=True,
            text=True,
            timeout=_LSOF_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _log.warning("could not list Codex working directories: %s", e)
        return None

    # 1 with nothing on stderr is lsof finding no such process.
    if result.returncode not in (0, 1) or result.stderr.strip():
        _log.warning("lsof failed listing Codex working directories: %s", result.stderr.strip())
        return None

    cwds: dict[str, str] = {}
    pid = ""
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            pid = line[1:]
        elif line.startswith("n") and pid:
            cwds[pid] = line[1:]

    servers = _app_server_pids(cwds)
    if servers is None:
        return None

    return {cwd for pid, cwd in cwds.items() if pid not in servers}


def gone(row: Row, directories: abc.Container[str] | None) -> bool:
    """True only when lsof answered and no Codex process works in the row's directory."""
    if directories is None or not is_untracked(row):
        return False

    cwd = row[2]
    return cwd not in directories and os.path.realpath(cwd) not in directories
