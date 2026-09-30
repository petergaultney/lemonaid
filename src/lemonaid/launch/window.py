"""The tmux window a lemon starts in: made, or respawned, but never taken from a live process."""

import dataclasses
import subprocess
import time
from collections import abc
from pathlib import Path

from ..log import get_logger

_log = get_logger("launch.window")

# What a harness shows before it reads its prompt, when a flag failed to skip it.
_STARTUP_DIALOGS = {
    "Trust this folder?": "Codex's folder-trust prompt",
    "Update available": "Codex's update prompt",
    "Is this a project you created or one you trust?": "Claude's folder-trust prompt",
}
_DIALOG_WAIT_SECONDS = 5.0


@dataclasses.dataclass(frozen=True)
class Pane:
    pane_id: str
    window_id: str


def _tmux(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def _panes(session: str, index: str) -> list[tuple[str, str, bool, str]]:
    """(pane ID, window ID, dead, current command) of each pane in the window, or []."""
    out = _tmux(
        "list-panes",
        "-s",
        "-t",
        f"={session}",
        "-F",
        "#{window_index}\t#{pane_id}\t#{window_id}\t#{pane_dead}\t#{pane_current_command}",
    ).stdout
    rows = [line.split("\t") for line in out.splitlines() if line.count("\t") == 4]
    return [
        (pane, window, dead == "1", command)
        for i, pane, window, dead, command in rows
        if i == index
    ]


def session_dir(session: str) -> Path | None:
    """The directory tmux session *session* was started in, or None if it doesn't exist."""
    result = _tmux("display-message", "-p", "-t", f"={session}:", "#{session_path}")
    return Path(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else None


def environment_args(environment: abc.Mapping[str, str]) -> list[str]:
    """tmux's `-e` arguments setting *environment* in a pane it starts."""
    return [arg for name, value in environment.items() for arg in ("-e", f"{name}={value}")]


def open_window(
    session: str, index: str, directory: Path, environment: abc.Mapping[str, str]
) -> tuple[Pane | None, str]:
    """A fresh pane at *session*:*index* started with *environment*, and "" - or None and why not.

    A window that doesn't exist is made; one whose only panes are dead is
    respawned. A live process there is refused, whatever it is.
    """
    panes = _panes(session, index)
    if live := [command for _, _, dead, command in panes if not dead]:
        return None, f"{session}:{index} is running {', '.join(live)}; not replacing it"

    if panes:
        pane, window, _, _ = panes[0]
        # With no command, tmux would rerun whatever the pane last ran.
        shell = _tmux("show-options", "-gv", "default-shell").stdout.strip()
        result = _tmux(
            "respawn-pane",
            "-t",
            pane,
            "-c",
            str(directory),
            *environment_args(environment),
            *([shell] if shell else []),
        )
        if result.returncode != 0:
            return None, f"Could not respawn {session}:{index}: {result.stderr.strip()}"

        return Pane(pane, window), ""

    result = _tmux(
        "new-window",
        "-d",
        "-t",
        f"={session}:{index}",
        "-c",
        str(directory),
        *environment_args(environment),
        "-P",
        "-F",
        "#{pane_id}\t#{window_id}",
    )
    pane, _, window = result.stdout.strip().partition("\t")
    if result.returncode != 0 or not window:
        return None, f"Could not make window {session}:{index}: {result.stderr.strip()}"

    return Pane(pane, window), ""


def run(pane: Pane, line: str) -> str:
    """Type *line* into *pane*'s shell. Returns an error, or ""."""
    result = _tmux("send-keys", "-t", pane.pane_id, line, "Enter")
    return "" if result.returncode == 0 else f"Could not start the lemon: {result.stderr.strip()}"


def startup_dialog(target: str, wait: float = _DIALOG_WAIT_SECONDS) -> str:
    """The startup dialog pane or window *target* shows after *wait* seconds, described, or "".

    Only reported: answering one means typing into a lemon, which lemonaid doesn't do.
    """
    time.sleep(wait)
    screen = _tmux("capture-pane", "-p", "-t", target).stdout
    found = [what for text, what in _STARTUP_DIALOGS.items() if text in screen]
    if found:
        _log.warning("%s stopped at %s", target, found[0])

    return found[0] if found else ""
