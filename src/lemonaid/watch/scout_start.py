"""Registering a lemon's push scout with the scout host, starting the host if none runs."""

import os
import subprocess
import sys
from pathlib import Path

from ..claude import session_socket
from ..inbox import db
from . import scout_roster

# Whichever lemon starts the host, it serves them all, so it keeps none of their identity.
_LEMON_VARIABLES = frozenset(
    {
        "CLAUDE_CODE_SESSION_ID",
        "CODEX_THREAD_ID",
        "LEMONAID_CHANNEL",
        "LEMONAID_HANDOFF_TOKEN",
        "TMUX_PANE",
        "WEZTERM_PANE",
        "CMUX_SURFACE_ID",
    }
)


def _spawn() -> None:
    log = scout_roster.log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as out:
        subprocess.Popen(
            [sys.executable, "-m", "lemonaid", "watch", "host"],
            env={
                **{k: v for k, v in os.environ.items() if k not in _LEMON_VARIABLES},
                "LEMONAID_DB": str(db.get_db_path()),
                "CLAUDE_CONFIG_DIR": str(session_socket.claude_dir()),
            },
            cwd=Path.home(),
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=out,
            start_new_session=True,
        )


def host(lemon_id: str, channel: str, thread: str, cwd: str) -> None:
    """Register the lemon's scout and start the host if none runs.

    A host that is exiting re-reads the registrations after releasing its lock, so a
    registration written while it exits is never left without a host.
    """
    scout_roster.register(lemon_id, channel, thread, cwd)
    if not scout_roster.host_pid():
        _spawn()
