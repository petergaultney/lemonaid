"""Every process from one `ps -A`, with each terminal named as `ps -t` names it.

On macOS `ps -A` takes most of a second to name every process's terminal, and
listings that overlap wait on one another: five at once take two seconds each. Device
numbers cost nothing, so on macOS it lists those and they are named here from `/dev`.
"""

import ctypes
import functools
import os
import stat
import subprocess
import sys

_WORDS = {"lstart": 5}  # columns ps writes as several words: "Mon Nov 23 11:19:05 2026"


@functools.cache
def sandboxed() -> bool:
    """Whether this process runs in a macOS sandbox, such as a Codex lemon's shell, where
    running the setuid `ps` fails with `Operation not permitted`."""
    if sys.platform != "darwin":
        return False

    check = ctypes.CDLL("/usr/lib/libSystem.B.dylib").sandbox_check
    check.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    return check(os.getpid(), None, 0) == 1


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


def listing(*columns: str, timeout: float | None) -> list[list[str]]:
    """Each process's `ps -A -ww -o` *columns*, the last split off whole, with its terminal
    as `ps -t` names it (`ttys004`, `pts/3`, `??`) in the place of a `tty` column.

    Raises `OSError` or `subprocess.SubprocessError` when `ps` can't say, and
    `PermissionError` without running it in a sandbox.
    """
    if sandboxed():
        raise PermissionError("a sandbox refuses to run ps")

    tty_column = "tdev" if sys.platform == "darwin" else "tty"
    spec = ",".join(f"{tty_column if c == 'tty' else c}=" for c in columns)
    result = subprocess.run(
        ["ps", "-A", "-ww", "-o", spec], capture_output=True, text=True, timeout=timeout
    )
    result.check_returncode()

    by_device = tty_column == "tdev"
    names = _terminal_names() if by_device and "tty" in columns else {}
    words = [_WORDS.get(c, 1) for c in columns[:-1]]
    found = []
    for line in result.stdout.splitlines():
        fields = line.split(None, sum(words))
        if len(fields) <= sum(words) or not fields[-1].strip():
            continue

        row, at = [], 0
        for column, count in zip(columns[:-1], words, strict=True):
            value = " ".join(fields[at : at + count])
            row.append(_tty_name(value, names) if column == "tty" and by_device else value)
            at += count
        found.append([*row, fields[-1].strip()])
    return found
