"""The command line of every process on a terminal, from one `ps` for all of them.

The watcher checks each live session's terminal every poll. One `ps -t` per
terminal is one fork per session every two seconds, which in a large inbox
process costs more than everything else the watcher does.
"""

import subprocess

from ..log import get_logger

_log = get_logger("watcher")


def by_tty() -> dict[str, list[str]] | None:
    """Each terminal's processes as `ps` args lines, keyed as `ps -t` names it (`ttys004`,
    `pts/3`), or None if `ps` could not say.
    """
    try:
        result = subprocess.run(
            ["ps", "-A", "-o", "tty=,args="], capture_output=True, text=True, timeout=2
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        _log.warning("could not list processes by terminal: %s", e)
        return None

    if result.returncode != 0:
        _log.warning("ps failed listing processes by terminal: %s", result.stderr.strip())
        return None

    found: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        tty, _, args = line.strip().partition(" ")
        if args.strip():
            found.setdefault(tty, []).append(args.strip())
    return found
