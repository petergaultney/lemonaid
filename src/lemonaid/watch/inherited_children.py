"""Reaping the child processes a process keeps across `exec`, as the scout host's restart does.

`exec` keeps a process's pid and its children, so a `ps` or `gh` a thread was still running
when the old code restarted would stay a zombie of the new code for good.
"""

import os
import subprocess
import threading

from .. import process_table
from ..log import get_logger

_log = get_logger("watch.inherited_children")


def _exited(pid: int) -> bool | None:
    """Reap child *pid* if it has exited: whether it had, or None when it is no child of
    this process, such as the `ps` that listed it."""
    try:
        return os.waitpid(pid, os.WNOHANG)[0] != 0
    except ChildProcessError:
        return None


def reap() -> None:
    """Reap this process's children: the finished ones now, each one still running in a
    thread of its own. Call it before starting any child of its own."""
    try:
        listed = process_table.listing("pid", "ppid", timeout=5)
    except (OSError, subprocess.SubprocessError) as error:
        _log.warning("could not list the processes kept across a restart: %s", error)
        return

    found = {pid: _exited(pid) for pid in (int(p) for p, pp in listed if int(pp) == os.getpid())}
    for pid, exited in found.items():
        if exited is False:
            threading.Thread(
                target=os.waitpid, args=(pid, 0), name=f"reap-{pid}", daemon=True
            ).start()
    if kept := [exited for exited in found.values() if exited is not None]:
        _log.info(
            "reaped %d processes kept across a restart; waiting on %d still running",
            kept.count(True),
            kept.count(False),
        )
