"""Renaming a tmux session."""

from .command import run

_TIMEOUT_SECONDS = 2.0


def session(old: str, new: str) -> str:
    """Rename session *old* to *new*; why it couldn't, or ""."""
    if run(["has-session", "-t", f"={new}"], timeout=_TIMEOUT_SECONDS).returncode == 0:
        return f"There is already a session named {new}"

    renamed = run(["rename-session", "-t", f"={old}", new], timeout=_TIMEOUT_SECONDS)
    if renamed.returncode != 0:
        return f"tmux could not rename {old}: {renamed.stderr.strip()}"

    return ""
