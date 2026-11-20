"""Telling whether a Codex session with no tty is still running.

A Codex TUI can run its sessions on a shared `codex app-server` daemon, whose hooks have
no terminal of the session's own, so its rows record no tty and every tty-keyed liveness
check passes them over. Such a session is gone once no Codex process, the daemon
included, runs its thread (`codex/processes.py`).
"""

import os
from collections import abc

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


def gone(row: Row, running: abc.Container[str] | None) -> bool:
    """True only when the running Codex threads are known and the row's isn't among them."""
    if running is None or not is_untracked(row):
        return False

    return row[0].removeprefix("codex:") not in running
