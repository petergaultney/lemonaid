"""Codex threads whose rollout files are open in a terminal process."""

import subprocess
from collections import defaultdict
from pathlib import Path

from ..lemon_watchers import untracked
from ..log import get_logger
from . import utils

_log = get_logger("codex.processes")
_TIMEOUT = 1


def thread_ttys() -> dict[str, set[str]] | None:
    try:
        files = subprocess.run(
            ["lsof", "-c", "codex", "-Fpn"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        if files.returncode not in (0, 1) or files.stderr.strip():
            return None
        paths: dict[str, set[str]] = defaultdict(set)
        pid = ""
        for line in files.stdout.splitlines():
            if line.startswith("p"):
                pid = line[1:]
            elif pid and line.startswith("n") and "/rollout-" in line and line.endswith(".jsonl"):
                paths[pid].add(line[1:])
        if not paths:
            return {}
        processes = subprocess.run(
            ["ps", "-o", "pid=,tty=,args=", "-p", ",".join(paths)],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        if processes.returncode not in (0, 1) or processes.stderr.strip():
            return None
    except (OSError, subprocess.SubprocessError) as error:
        _log.debug("could not inspect Codex terminals: %s", error)
        return None

    result: dict[str, set[str]] = defaultdict(set)
    for line in processes.stdout.splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) != 3:
            continue
        pid, tty, command = fields
        args = command.split()
        # App-server rollouts can belong to several independent terminals.
        if tty in {"?", "??", "-"} or untracked.is_app_server(args):
            continue
        for path in paths.get(pid, ()):
            meta = utils.read_session_meta(Path(path))
            if not meta or utils.is_spawned_thread(meta):
                continue
            if thread := meta.get("id"):
                result[thread].add(tty if tty.startswith("/dev/") else f"/dev/{tty}")
    return dict(result)
