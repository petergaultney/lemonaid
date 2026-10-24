"""Which Claude session each terminal is running, from the sessions Claude Code lists."""

import calendar
import os
import subprocess
import time

from ..log import get_logger
from . import session_socket

_log = get_logger("claude.live_sessions")

_PS_TIMEOUT_SECONDS = 2
_START_FORMAT = "%a %b %d %H:%M:%S %Y"


def _started(text: str, utc: bool) -> float | None:
    try:
        parsed = time.strptime(text, _START_FORMAT)
    except ValueError:
        return None

    return calendar.timegm(parsed) if utc else time.mktime(parsed)


def _listing(pids: list[int]) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "-o", "pid=,tty=,lstart=,args=", "-p", ",".join(map(str, pids))],
            capture_output=True,
            text=True,
            timeout=_PS_TIMEOUT_SECONDS,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("could not list Claude processes: %s", e)
        return None

    # 1 is `ps` finding none of the pids, which says every listed session is gone.
    return result.stdout if result.returncode in (0, 1) else None


def by_tty() -> dict[str, set[str]] | None:
    """The full session ids of the Claude processes on each tty (`/dev/ttys001`), or None
    if `ps` could not say.

    A Claude process lists the one session it is running in `~/.claude/sessions/<pid>.json`,
    including after an in-app `/resume`. A file left by a process that died can name a
    reused pid, so a session counts only when that pid is a `claude` process that started
    when the file says it did.
    """
    sessions = session_socket.live()
    if not sessions:
        return {}

    listing = _listing([s.pid for s in sessions])
    if listing is None:
        return None

    processes = {}
    for line in listing.splitlines():
        fields = line.split(maxsplit=8)  # lstart is five words: "Sat Oct 24 09:31:18 2026"
        if len(fields) >= 8 and os.path.basename(fields[7]) == "claude":
            processes[fields[0]] = (fields[1], _started(" ".join(fields[2:7]), utc=False))

    found: dict[str, set[str]] = {}
    for session in sessions:
        tty, started = processes.get(str(session.pid), ("??", None))
        if tty in ("?", "??", "-") or started is None:
            continue
        if started != _started(session.proc_start, utc=True):
            continue
        found.setdefault(f"/dev/{tty}", set()).add(session.session_id)
    return found
