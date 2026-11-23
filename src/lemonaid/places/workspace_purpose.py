"""Live lemon panes, independent of archived or missing inbox rows."""

import shlex
import subprocess
from pathlib import Path

from .. import process_table
from . import windows

_HARNESSES = {"claude", "codex", "opencode", "openclaw"}


def lemon_panes(name: str) -> set[str] | None:
    panes = windows.query("list-panes", "-s", "-t", "=" + name, "-F", "#{pane_id}\t#{pane_tty}")
    if panes is None:
        return None
    try:
        listed = process_table.listing("tty", "args", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None

    ttys: set[str] = set()
    for tty, args in listed:
        try:
            argv = shlex.split(args)
        except ValueError:
            argv = args.split()
        if not argv:
            continue
        executable = Path(argv[0]).name
        script = Path(argv[1]).stem if len(argv) > 1 else ""
        if executable in _HARNESSES or (executable in {"node", "nodejs"} and script in _HARNESSES):
            ttys.add(tty.removeprefix("/dev/"))

    return {
        pane
        for line in panes
        for pane, tty in [line.split("\t", 1)]
        if tty.removeprefix("/dev/") in ttys
    }
