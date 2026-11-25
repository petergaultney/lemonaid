"""Registering a lemon's push scout with the scout host, starting the host if none runs."""

import os
import shutil
import subprocess
import sys
import uuid
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
        "LEMONAID_LAUNCH_TOKEN",
        "TMUX_PANE",
        "WEZTERM_PANE",
        "CMUX_SURFACE_ID",
    }
)


_UNIT_OWN = frozenset({"INVOCATION_ID", "JOURNAL_STREAM", "SYSTEMD_EXEC_PID"})  # systemd sets these


def _in_own_unit(command: list[str], env: dict[str, str], log: Path) -> list[str]:
    """*command* as a transient systemd user unit, so the host outlives the unit that started it.

    A process started from inside a service (an OpenClaw gateway's shell command, say) is
    killed with that service's cgroup when the service restarts, however detached it is.
    """
    return [
        "systemd-run",
        "--user",
        "--collect",
        "--quiet",
        f"--unit=lemonaid-scout-host-{uuid.uuid4().hex[:8]}",  # a second host exits on the lock
        f"--working-directory={Path.home()}",
        f"--property=StandardOutput=append:{log}",
        f"--property=StandardError=append:{log}",
        *(f"--setenv={k}={v}" for k, v in env.items() if k not in _UNIT_OWN and "\n" not in v),
        *command,
    ]


def _spawn() -> None:
    log = scout_roster.log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "lemonaid", "watch", "host"]
    env = {
        **{k: v for k, v in os.environ.items() if k not in _LEMON_VARIABLES},
        "LEMONAID_DB": str(db.get_db_path()),
        "CLAUDE_CONFIG_DIR": str(session_socket.claude_dir()),
    }
    if os.environ.get("INVOCATION_ID") and shutil.which("systemd-run"):
        subprocess.run(_in_own_unit(command, env, log), check=True, timeout=30)
        return

    with log.open("a") as out:
        subprocess.Popen(
            command,
            env=env,
            cwd=Path.home(),
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=out,
            start_new_session=True,
        )


def ensure_host() -> None:
    if not scout_roster.host_pid():
        _spawn()


def host(lemon_id: str, channel: str, thread: str, cwd: str) -> None:
    """Register the lemon's scout and start the host if none runs.

    A host that is exiting re-reads the registrations after releasing its lock, so a
    registration written while it exits is never left without a host.
    """
    scout_roster.register(lemon_id, channel, thread, cwd)
    ensure_host()
