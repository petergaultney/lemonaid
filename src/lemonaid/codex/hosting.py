"""Whether a Codex hook was spawned by the shared app-server rather than a TUI.

A Codex TUI can run its sessions on a `codex app-server` daemon that the first
TUI started. The daemon keeps that TUI's controlling tty and environment, so a
hook under it reports the first TUI's pane for every session on the machine, and
no tty at all once that pane closes. Neither says where this session is.
"""

import os
import subprocess

from ..lemon_watchers import untracked
from ..log import get_logger

_log = get_logger("codex.hosting")

_ANCESTOR_DEPTH = 10
_PROBE_TIMEOUT_SECONDS = 5


def under_app_server() -> bool:
    pid = os.getpid()
    for _ in range(_ANCESTOR_DEPTH):
        try:
            result = subprocess.run(
                ["ps", "-o", "ppid=,args=", "-p", str(pid)],
                capture_output=True,
                text=True,
                check=True,
                timeout=_PROBE_TIMEOUT_SECONDS,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            _log.warning("ps failed walking up from pid %d: %s", pid, e)
            return False

        ppid, _, args = result.stdout.strip().partition(" ")
        if untracked.is_app_server(args.split()):
            return True

        if not ppid.isdigit() or int(ppid) <= 1:
            return False

        pid = int(ppid)

    return False
