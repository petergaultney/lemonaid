"""The command line of every process on a terminal, from one `ps` for all of them.

The watcher checks each live session's terminal every poll. One `ps -t` per
terminal is one fork per session every two seconds, which in a large inbox
process costs more than everything else the watcher does.

On macOS `ps` takes most of a second to name every process's terminal, so it
lists device numbers instead and they are named here from `/dev`.
"""

import os
import stat
import subprocess
import sys

from ..log import get_logger

_log = get_logger("watcher")


def _terminal_names() -> dict[int, str]:
    names = {}
    with os.scandir("/dev") as entries:
        for entry in entries:
            if not entry.name.startswith("tty") and entry.name != "console":
                continue
            try:
                found = os.stat(entry.path)
            except OSError:
                continue  # closed since the scan began
            if stat.S_ISCHR(found.st_mode):
                names[found.st_rdev] = entry.name
    return names


def _tty_name(tdev: str, names: dict[int, str]) -> str:
    """`ps -o tty`'s name for a `ps -o tdev` value such as `16/1`; `??` for no terminal."""
    major, _, minor = tdev.partition("/")
    if not (major.isdigit() and minor.isdigit()):
        return tdev

    return names.get(os.makedev(int(major), int(minor)), "??")


def listing(column: str) -> list[tuple[str, str]] | None:
    """Every process's terminal, as `ps -t` names it (`ttys004`, `pts/3`, `??`), and its
    `ps -o` *column*, or None if `ps` could not say.
    """
    tty_column = "tdev" if sys.platform == "darwin" else "tty"
    try:
        result = subprocess.run(
            ["ps", "-A", "-o", f"{tty_column}=,{column}="],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        _log.warning("could not list processes by terminal: %s", e)
        return None

    if result.returncode != 0:
        _log.warning("ps failed listing processes by terminal: %s", result.stderr.strip())
        return None

    names = _terminal_names() if tty_column == "tdev" else {}
    found = []
    for line in result.stdout.splitlines():
        tty, _, value = line.strip().partition(" ")
        if value.strip():
            found.append((_tty_name(tty, names), value.strip()))
    return found


def by_tty() -> dict[str, list[str]] | None:
    """Each terminal's processes as `ps` args lines, keyed as `ps -t` names it (`ttys004`,
    `pts/3`), or None if `ps` could not say.
    """
    listed = listing("args")
    if listed is None:
        return None

    found: dict[str, list[str]] = {}
    for tty, args in listed:
        found.setdefault(tty, []).append(args)
    return found
