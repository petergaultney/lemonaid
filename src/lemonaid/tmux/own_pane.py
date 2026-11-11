"""A lemon whose harness crashed goes back into its own pane, left idle at a shell prompt.

The pane keeps its place in its window and its tty; tmux's `respawn-pane` replaces the
idle shell with a fresh one started in the lemon's directory and environment, so the
resume line types into it like a new window's.
"""

import subprocess
import typing as ty
from collections import abc

from ..inbox import db
from ..launch import window as launch_window
from ..launch.restart import process
from ..log import get_logger
from . import command

_log = get_logger("tmux.own_pane")

_TIMEOUT_SECONDS = 5


class Pane(ty.NamedTuple):
    pane_id: str
    server_start: int  # the server it was recorded on, which a pane id is unique within
    where: str  # session:window, as a person names it
    shell: str  # its shell process's start time and command line, when it was found idle


def _interactive(argv: str) -> bool:
    """Whether a shell's command line runs no command or script (`-c`, a file argument)."""
    options = argv.split()[1:]
    return all(each.startswith("-") for each in options) and not any(
        "c" in each[1:] for each in options if not each.startswith("--")
    )


def _prompting(shell_pid: str) -> str:
    """The shell's start time and command line, when it is interactive and holds its
    terminal's foreground: at its prompt, rather than running a command or script, which
    tmux would also name after the shell. "" otherwise."""
    try:
        result = subprocess.run(
            ["ps", "-o", "pgid=,tpgid=,lstart=,command=", "-p", shell_pid],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("could not ask ps about pid %s: %s", shell_pid, e)
        return ""

    fields = result.stdout.strip().split(None, 7)
    if len(fields) != 8 or not fields[0] == fields[1] != "0" or not _interactive(fields[7]):
        return ""

    return " ".join(fields[2:])


def _at_shell(pane_id: str, server_start: int) -> Pane | None:
    """The pane, when it still runs on that server with its shell idle at a prompt."""
    try:
        result = command.run(
            [
                "display-message",
                "-p",
                "-t",
                pane_id,
                "#{start_time}|#{session_name}:#{window_index}|#{pane_current_command}|#{pane_pid}",
            ],
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("could not ask tmux about pane %s: %s", pane_id, e)
        return None

    started, where, running, shell_pid = [*result.stdout.strip().split("|"), "", "", "", ""][:4]
    if result.returncode or started != str(server_start) or running not in process.SHELLS:
        return None

    shell = _prompting(shell_pid)
    return Pane(pane_id, server_start, where, shell) if shell else None


def _idle(metadata: abc.Mapping[str, ty.Any]) -> Pane | None:
    match metadata.get("tmux_pane_identity"):
        case [str(pane_id), int(server_start)]:
            return _at_shell(pane_id, server_start)
        case _:
            return None


def idle(rows: abc.Iterable[db.Notification]) -> dict[str, Pane]:
    """Each row whose own pane is idle at a shell now, by channel. Rows recording the same
    pane (one lemon crashed there, then another) give it to the one heard from last."""
    owners: dict[Pane, db.Notification] = {}
    for row in sorted(rows, key=lambda r: max(r.created_at, r.turn_at or 0.0), reverse=True):
        if (pane := _idle(row.metadata)) and pane not in owners:
            owners[pane] = row
    return {row.channel: pane for pane, row in owners.items()}


def respawn(pane: Pane, cwd: str, environment: abc.Mapping[str, str]) -> tuple[str, str]:
    """Start a fresh shell in *pane*, in *cwd* with *environment*: (its id, why not or "").

    The pane is checked again first, and its shell must be the same process at its prompt:
    restore plans every lemon before starting any, and someone may have started work in it
    (an `exec` replaces the shell's program), or an earlier attempt's lemon may still be
    starting.
    """
    now = _at_shell(pane.pane_id, pane.server_start)
    if now is None or now.shell != pane.shell:
        return "", "its own pane is no longer idle at the shell it was found at"

    try:
        result = command.run(
            [
                "respawn-pane",
                "-k",
                "-t",
                pane.pane_id,
                "-c",
                cwd,
                *launch_window.environment_args(environment),
            ],
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return "", str(e)

    return (pane.pane_id, "") if result.returncode == 0 else ("", result.stderr.strip())
