"""Live lemon panes, independent of archived or missing inbox rows."""

import shlex
import subprocess
from pathlib import Path

from . import windows

_HARNESSES = {"claude", "codex", "opencode", "openclaw"}


def lemon_panes(name: str) -> set[str] | None:
    panes = windows.query("list-panes", "-s", "-t", "=" + name, "-F", "#{pane_id}\t#{pane_tty}")
    if panes is None:
        return None
    try:
        result = subprocess.run(
            ["ps", "-axo", "tty=,args="], capture_output=True, text=True, check=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None

    ttys: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        try:
            argv = shlex.split(parts[1])
        except ValueError:
            argv = parts[1].split()
        if not argv:
            continue
        executable = Path(argv[0]).name
        script = Path(argv[1]).stem if len(argv) > 1 else ""
        if executable in _HARNESSES or (executable in {"node", "nodejs"} and script in _HARNESSES):
            ttys.add(parts[0].removeprefix("/dev/"))

    return {
        pane
        for line in panes
        for pane, tty in [line.split("\t", 1)]
        if tty.removeprefix("/dev/") in ttys
    }
