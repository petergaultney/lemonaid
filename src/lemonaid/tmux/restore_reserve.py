"""Windows restore makes ahead of their lemons, so tmux's sessions and windows come back in
the order tmux first made them, whatever order the lemons start in.

A reserved window runs a placeholder that names the lemon coming there, not a shell, so
nothing typed into it before then runs. Starting the lemon replaces the placeholder, in the
same pane, with the shell tmux would start in a new window, so the window keeps its index
however the session numbers its windows.

A reserved window someone has split, or started anything else in, is theirs: restore
neither starts a lemon in it nor closes it.
"""

import subprocess
import typing as ty
from collections import abc

from ..launch import window as launch_window
from ..log import get_logger
from ..restore import run
from . import command, own_pane

_log = get_logger("tmux.restore_reserve")

_MARK = "lemonaid-restore"  # the placeholder's $0, which its pane's start command shows
_TIMEOUT_SECONDS = 5


def _placeholder(name: str) -> list[str]:
    """The command a window reserved for lemon *name* runs until the lemon starts."""
    return [
        "sh",
        "-c",
        'printf "%s\\n" "$1"; exec sleep 2147483647',
        _MARK,
        f"lemonaid restore will start {name} here.",
    ]


def _tmux(*args: str) -> tuple[str, str]:
    """(what `tmux *args` printed, why it failed or "")."""
    try:
        done = command.run(args, timeout=_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as e:
        return "", str(e)

    if done.returncode:
        return "", done.stderr.strip() or f"exit {done.returncode}"

    return done.stdout.strip(), ""


def _placeholder_pane(window: str) -> tuple[str, str]:
    """(the pane in *window* still running the placeholder alone, why not or "")."""
    found, why = _tmux("list-panes", "-t", window, "-F", "#{pane_id}|#{pane_start_command}")
    panes = found.splitlines()
    if why:
        return "", why

    if len(panes) != 1:
        return "", "someone opened another pane in its reserved window"

    pane, _, started = panes[0].partition("|")
    if _MARK not in started:
        return "", "someone started something else in its reserved window"

    return pane, ""


def _take(window: str, cwd: str, environment: abc.Mapping[str, str]) -> str:
    """Replace the placeholder in *window*, reserved by restore, with a shell in *cwd* with
    *environment*: why not, or "".

    The shell is what tmux starts in a new window: `default-command` if set, else
    `default-shell` as a login shell. Without a command, `respawn-pane` would start the
    placeholder again.
    """
    pane, why = _placeholder_pane(window)
    if why:
        return why

    found, why = _tmux("display-message", "-p", "-t", pane, "#{default-command}|#{default-shell}")
    configured, _, shell = found.rpartition("|")
    if why or not (configured or shell):
        return why or "tmux names no shell to start"

    return _tmux(
        "respawn-pane",
        "-k",
        "-t",
        pane,
        "-c",
        cwd,
        *launch_window.environment_args(environment),
        *([configured] if configured else [shell, "-l"]),
    )[1]


Open = abc.Callable[[run.Spot, str, abc.Mapping[str, str], abc.Sequence[str]], tuple[str, str]]
"""Open a spot's window in a cwd with an environment, running a command rather than a shell
when one is given: (the window, why not or "")."""


class Windows(ty.NamedTuple):
    reserve: abc.Callable[[abc.Sequence[tuple[run.Spot, str, str]]], None]
    release: abc.Callable[[run.Spot], None]
    open: abc.Callable[[run.Spot, str, abc.Mapping[str, str]], tuple[str, str]]


def windows(open_window: Open, close_window: abc.Callable[[str], None]) -> Windows:
    """Restore's `reserve`, `release` and `open` for one restore, which share the windows
    reserved so far. A lemon going back into its own pane needs no window reserved."""
    reserved: dict[str, str] = {}

    def reserve(spots: abc.Sequence[tuple[run.Spot, str, str]]) -> None:
        for to, cwd, name in spots:
            if not isinstance(to.at, own_pane.Pane):
                window, _ = open_window(to, cwd, {}, _placeholder(name))
                if window:
                    reserved[to.where] = window

    def release(to: run.Spot) -> None:
        window = reserved.pop(to.where, "")
        if not window:
            return

        if why := _placeholder_pane(window)[1]:
            _log.warning("leaving the window reserved at %s open: %s", to.where, why)
        else:
            close_window(window)

    def open_spot(to: run.Spot, cwd: str, environment: abc.Mapping[str, str]) -> tuple[str, str]:
        window = reserved.pop(to.where, "")
        if not window:
            return open_window(to, cwd, environment, ())

        if why := _take(window, cwd, environment):
            _log.warning("not starting %s in its reserved window: %s", to.where, why)
            return open_window(to, cwd, environment, ())

        return window, ""

    return Windows(reserve, release, open_spot)
