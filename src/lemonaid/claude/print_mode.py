"""Whether a hook is running for a `claude -p` session, which never belongs in the inbox."""

import os
import subprocess
from pathlib import Path

from ..inbox.channel import UnidentifiedSession
from . import launch_args

_MAX_DEPTH = 6
_PRINT_FLAGS = ("-p", "--print")


class PrintSession(UnidentifiedSession):
    """The hook belongs to a one-shot `claude -p` run: nobody can switch to it or answer it."""


def _parent(pid: int) -> int:
    try:
        out = subprocess.run(
            ["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return int(out)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0


def is_print_session(pid: int | None = None) -> bool:
    """True when the nearest `claude` ancestor of *pid* (default: this process) was started with -p."""
    pid = pid or os.getpid()
    for _ in range(_MAX_DEPTH):
        pid = _parent(pid)
        if pid <= 1:
            return False

        argv = launch_args.argv(pid)
        if argv and Path(argv[0]).name == "claude":
            return any(flag in argv[1:] for flag in _PRINT_FLAGS)

    return False
