"""Runs a tmux command; callers outside `lemonaid/tmux/` go through this."""

import subprocess
from collections import abc

from . import navigation


def run(
    args: abc.Sequence[str],
    socket: str | None = None,
    *,
    check: bool = False,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run `tmux *args` (against *socket* when given) with captured text output."""
    return subprocess.run(
        [*navigation.server_args(socket), *args],
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout,
    )
