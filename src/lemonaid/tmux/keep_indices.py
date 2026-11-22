"""Closing or moving a window without tmux renumbering the other windows of its session.

With `renumber-windows` on, tmux renumbers a session's windows whenever one closes or
moves away, while restore puts every lemon at its recorded index and proves it running
there. The option is turned off for that session around the one command, then put back
as it was.
"""

import subprocess

from ..log import get_logger
from . import command

_log = get_logger("tmux.keep_indices")

_TIMEOUT_SECONDS = 5


def _tmux(*args: str) -> tuple[str, str]:
    """(what `tmux *args` printed, why it failed or "")."""
    try:
        done = command.run(args, timeout=_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as e:
        return "", str(e)

    if done.returncode:
        return "", done.stderr.strip() or f"exit {done.returncode}"

    return done.stdout.strip(), ""


def run(target: str, *args: str) -> str:
    """Run `tmux *args`, which closes or moves a window of *target*'s session, leaving the
    session's other windows at their indices: why it failed, or ""."""
    found, why = _tmux("display-message", "-p", "-t", target, "#{session_id}|#{renumber-windows}")
    session, _, renumbering = found.partition("|")
    if why or renumbering not in ("1", "on"):
        return _tmux(*args)[1]

    own = _tmux("show-options", "-t", session, "-qv", "renumber-windows")[0]
    _tmux("set-option", "-t", session, "renumber-windows", "off")
    try:
        return _tmux(*args)[1]
    finally:
        restored = (
            ("set-option", "-t", session, "renumber-windows", own)
            if own
            else ("set-option", "-u", "-t", session, "renumber-windows")
        )
        if why := _tmux(*restored)[1]:
            _log.warning("could not put back renumber-windows for %s: %s", session, why)
