"""Putting a session back when selecting it finds its pane gone.

The archive records where work happened, so a missing pane is a place to pick
work back up rather than a dead end. What goes back is the row's own session,
resumed with its harness's resume command, in the tmux template's layout. A row
with no way to resume it is refused: the template's harness window starts one
particular agent, which for a row from any other harness is a stranger in its
worktree.
"""

import subprocess
from pathlib import Path
from typing import Any

from ..config import Config
from ..log import get_logger
from ..resume import build_resume_command
from . import session

_log = get_logger("tmux.recreate")


def _session_path(name: str) -> str | None:
    """The directory tmux session *name* was started in, or None if there is no such session."""
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", f"={name}:", "#{session_path}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None

    return result.stdout.strip() or None


def recreate(metadata: dict[str, Any], config: Config) -> bool:
    """Resume the notification's session in a new tmux session rooted at its cwd.

    A tmux session already holding the name is refused rather than switched to:
    it may run another agent entirely, as an earlier recreate that started the
    wrong harness did.
    """
    cwd = metadata.get("cwd")
    if not cwd or not Path(cwd).is_dir():
        return False

    channel = metadata.get("channel", "")
    resumable = build_resume_command(config, channel, metadata)
    if resumable is None:
        _log.warning("not recreating %s: no way to resume it", channel or "a session")
        return False

    name = session.sanitize_name(metadata.get("name", "") or session.auto_session_name(Path(cwd)))
    existing = _session_path(name)
    if existing is not None:
        # No pane in the row's directory runs its harness, or this would not be
        # called, so whatever holds the name is not this session.
        _log.warning("not recreating %s: session %r already exists in %s", channel, name, existing)
        return False

    _, argv = resumable
    error = session.spawn_session(
        cwd=cwd,
        config=config.tmux_session,
        resume_argv=argv,
        channel=channel,
        session_metadata=metadata,
        session_name=name,
    )
    if error:
        _log.warning("could not recreate a session in %s: %s", cwd, error)
        return False

    return True
