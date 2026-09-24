"""What tmux knows about a session that helps find its brief."""

import os
import subprocess
from pathlib import Path

LEMON_NAME_ENV = "LEMON_NAME"


def _tmux(*args: str) -> str:
    """A tmux command's stdout, or "" when it fails (no server, no such session)."""
    result = subprocess.run(["tmux", *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def current_session() -> str:
    """The session of the calling pane, or "" outside tmux."""
    pane = os.environ.get("TMUX_PANE")
    if not pane:
        return ""

    return _tmux("display-message", "-p", "-t", pane, "#{session_name}")


def session_dir(session: str) -> Path | None:
    """The directory a session was started in, which for a place is the place."""
    path = _tmux("display-message", "-p", "-t", f"={session}:", "#{session_path}")
    return Path(path) if path else None


def lemon_name(session: str) -> str:
    """The session's `LEMON_NAME`, or "" when it has none."""
    line = _tmux("show-environment", "-t", f"={session}", LEMON_NAME_ENV)
    prefix = f"{LEMON_NAME_ENV}="
    return line.removeprefix(prefix) if line.startswith(prefix) else ""


def names(session: str, *others: str) -> list[str]:
    """What a brief for this session could be named after, most specific first."""
    return [n for n in (lemon_name(session) if session else "", session, *others) if n]
