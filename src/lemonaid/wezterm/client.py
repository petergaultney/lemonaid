"""Running `wezterm cli` against a particular WezTerm instance.

Each WezTerm GUI has its own mux socket, named in its panes' `WEZTERM_UNIX_SOCKET`;
without it, `wezterm cli` picks an instance by itself, which may be another one.
"""

import json
import os
import subprocess
import typing as ty

from ..log import get_logger

_log = get_logger("wezterm.client")

_TIMEOUT_SECONDS = 5
SOCKET_ENV = "WEZTERM_UNIX_SOCKET"


def run(args: ty.Sequence[str], socket: str | None = None) -> subprocess.CompletedProcess[str]:
    """`wezterm cli *args`; a failure to start it at all comes back as exit 127."""
    env = {**os.environ, SOCKET_ENV: socket} if socket else None
    try:
        return subprocess.run(
            ["wezterm", "cli", *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _log.warning("wezterm cli %s failed: %s", " ".join(args[:1]), e)
        return subprocess.CompletedProcess(["wezterm", "cli", *args], 127, "", str(e))


def panes(socket: str | None = None) -> list[dict[str, ty.Any]] | None:
    """Every pane `wezterm cli list` reports, or None when it can't."""
    listed = run(["list", "--format", "json"], socket)
    if listed.returncode != 0:
        return None

    try:
        found = json.loads(listed.stdout)
    except json.JSONDecodeError:
        return None

    return found if isinstance(found, list) else None
