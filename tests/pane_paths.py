"""Waiting for a real tmux server's panes to report their directories.

tmux reads a pane's directory from its process, so a pane it has just created reports
the server's own directory until the process has moved into the one it was given.
"""

import subprocess
import time
from collections import abc
from pathlib import Path

import pytest


def settled(
    tmux: abc.Callable[..., subprocess.CompletedProcess], *directories: Path, timeout: float = 5
) -> None:
    """Wait until the server's panes are in exactly *directories*, one pane each."""
    want = sorted(str(d.resolve()) for d in directories)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        listed = tmux("list-panes", "-a", "-F", "#{pane_current_path}").stdout.split("\n")
        if sorted(str(Path(p).resolve()) for p in listed if p) == want:
            return

        time.sleep(0.05)
    pytest.fail(f"tmux panes never reported {want}")
