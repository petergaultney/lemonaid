"""What a restored lemon's tmux pane shows: whether its harness still runs, and its screen."""

import subprocess

from ..restore import report

_TIMEOUT_SECONDS = 5


def _tmux(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["tmux", *args], capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.SubprocessError):
        return None

    return result.stdout if result.returncode == 0 else None


def _has_children(pid: str) -> bool:
    """Whether process *pid* has a child: the pane's shell running the typed line."""
    try:
        return subprocess.run(["pgrep", "-P", pid], capture_output=True).returncode == 0
    except OSError:
        return False


def seen(target: str) -> report.Seen:
    """What the pane at *target* shows; a pane that's gone shows nothing running.

    The pane's own process is the shell the lemon's line was typed into, so a
    harness that exited leaves it with no children, whatever the shell is called.
    """
    pid = (_tmux("display-message", "-p", "-t", target, "#{pane_pid}") or "").strip()
    if not pid:
        return report.Seen(False, "")

    return report.Seen(_has_children(pid), _tmux("capture-pane", "-p", "-J", "-t", target) or "")
