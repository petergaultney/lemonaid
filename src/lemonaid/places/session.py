"""Inspect a named tmux session before a session-only toss."""

import subprocess


def exists(name: str) -> bool:
    try:
        found = subprocess.run(
            ["tmux", "has-session", "-t", f"={name}"], capture_output=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return False

    return found.returncode == 0
