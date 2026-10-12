"""Inspect a named tmux session before a session-only toss."""

import subprocess

from .. import tmux


def exists(name: str) -> bool:
    try:
        found = tmux.run(["has-session", "-t", f"={name}"], timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False

    return found.returncode == 0
