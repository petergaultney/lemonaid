"""The command line of every process on a terminal, from one `ps` for all of them.

The watcher checks each live session's terminal every poll. One `ps -t` per
terminal is one fork per session every two seconds, which in a large inbox
process costs more than everything else the watcher does.
"""

import os
import subprocess
import typing as ty
from collections import abc

from .. import process_table
from ..log import get_logger

_log = get_logger("watcher")
_REUSE_SECONDS = 30.0


def _ps(*columns: str) -> list[list[str]] | None:
    try:
        return process_table.listing(*columns, timeout=2)
    except subprocess.CalledProcessError as e:
        _log.warning("ps failed listing processes by terminal: %s", e.stderr.strip())
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("could not list processes by terminal: %s", e)
    return None


def listing(column: str) -> list[tuple[str, str]] | None:
    """Every process's terminal, as `ps -t` names it (`ttys004`, `pts/3`, `??`), and its
    `ps -o` *column*, or None if `ps` could not say.
    """
    found = _ps("tty", column)
    return None if found is None else [(tty, value) for tty, value in found]


def _grouped(listed: abc.Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for tty, args in listed:
        found.setdefault(tty, []).append(args)
    return found


def by_tty() -> dict[str, list[str]] | None:
    """Each terminal's processes as `ps` args lines, keyed as `ps -t` names it (`ttys004`,
    `pts/3`), or None if `ps` could not say.
    """
    listed = listing("args")
    return None if listed is None else _grouped(listed)


def _running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class _Listed(ty.NamedTuple):
    at: float
    by_tty: dict[str, list[str]]
    harnesses: frozenset[int]  # the pids of the harnesses in it


class Reused:
    """`by_tty`, listed again only when a harness it names may have exited.

    A listing is reused while every harness in it still runs and it is under
    `_REUSE_SECONDS` old, so a harness it names is still there; one that started
    since is missing from it, which is why a caller about to act on an absence asks
    for a *fresh* listing first. Telling whether a pid still runs costs no fork; a
    listing costs a `ps` that walks every process.
    """

    def __init__(self, is_harness: abc.Callable[[str], bool]) -> None:
        self._is_harness = is_harness
        self._listed: _Listed | None = None

    def _list(self, now: float) -> _Listed | None:
        found = _ps("pid", "tty", "args")
        if found is None:
            return None

        return _Listed(
            now,
            _grouped((tty, args) for _, tty, args in found),
            frozenset(int(pid) for pid, _, args in found if self._is_harness(args)),
        )

    def by_tty(self, fresh: bool, now: float) -> dict[str, list[str]] | None:
        listed = self._listed
        if (
            fresh
            or listed is None
            or now - listed.at >= _REUSE_SECONDS
            or not all(map(_running, listed.harnesses))
        ):
            listed = self._listed = self._list(now)
        return None if listed is None else listed.by_tty
