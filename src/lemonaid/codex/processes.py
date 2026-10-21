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
        paths = _open_paths(files.stdout)
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

    return _owners(paths, processes.stdout)


def _owners(paths: dict[str, set[str]], listing: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for line in listing.splitlines():
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


def _open_paths(listing: str) -> dict[str, set[str]]:
    paths: dict[str, set[str]] = defaultdict(set)
    pid = ""
    for line in listing.splitlines():
        if line.startswith("p"):
            pid = line[1:]
        elif pid and line.startswith("n") and "/rollout-" in line and line.endswith(".jsonl"):
            paths[pid].add(line[1:])
    return paths


def thread_ttys_for_tty(tty: str) -> dict[str, set[str]] | None:
    """Inspect only this terminal so notify does not depend on a machine-wide ps."""
    try:
        listing = subprocess.run(
            ["ps", "-t", tty.removeprefix("/dev/"), "-o", "pid=,tty=,args="],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        if listing.returncode not in (0, 1) or listing.stderr.strip():
            return None
        pids = []
        for line in listing.stdout.splitlines():
            fields = line.split(maxsplit=2)
            if len(fields) == 3 and Path(fields[2].split()[0]).name.startswith("codex"):
                pids.append(fields[0])
        if not pids:
            return {}
        files = subprocess.run(
            ["lsof", "-a", "-c", "codex", "-p", ",".join(pids), "-Fpn"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        if files.returncode not in (0, 1) or files.stderr.strip():
            return None
        return _owners(_open_paths(files.stdout), listing.stdout)
    except (OSError, subprocess.SubprocessError) as error:
        _log.debug("could not inspect Codex terminal %s: %s", tty, error)
        return None
