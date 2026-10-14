"""Bring back, through tmux, a lemon that won't read the message it was just sent.

Every command goes to the tmux server the lemon was recorded on: pane ids are
per server, so `%3` on the sender's server is some other pane.
"""

import re
import subprocess
import time

from .. import tmux
from ..config import BackendConfig, Config
from ..inbox import db
from ..launch import window
from ..restore import launch
from ..tmux import navigation, submit
from . import wake

_SUBMIT_PAUSE_SECONDS = 1.0  # lets the composer take the typed text before Enter
# Claude's bare composer marker and Codex's empty composer placeholder. Dialogs also use the marker.
_EMPTY_COMPOSER = re.compile(r"\s*(?:\u276f|\u203a Ask Codex to do anything)\s*")


def _tmux(row: db.Notification, *args: str) -> subprocess.CompletedProcess[str]:
    return tmux.run(args, row.metadata.get("tmux_socket"))


def _pane(row: db.Notification) -> str:
    tty = str(row.metadata.get("tty") or "")
    if not tty:
        return ""

    try:
        _, pane = navigation.get_pane_for_tty(tty, row.metadata.get("tmux_socket"))
    except navigation.TmuxUnavailable:
        return ""

    return pane or ""


def screen(row: db.Notification) -> str | None:
    """What *row*'s pane shows now, or None when its pane can't be found."""
    pane = _pane(row)
    if not pane:
        return None

    captured = _tmux(row, "capture-pane", "-p", "-t", pane)
    return captured.stdout if captured.returncode == 0 else None


def ready_for_input(screen: str) -> bool:
    """Whether *screen* shows an empty composer and no dialog."""
    return not window.dialog_in(screen) and any(
        _EMPTY_COMPOSER.fullmatch(line) for line in screen.splitlines()
    )


def start(row: db.Notification, config: Config, text: str = wake.PROMPT) -> str:
    """Resume *row*'s exited harness on *text* in a new window of its tmux session. Returns why not, or ""."""
    session = str(row.metadata.get("tmux_session") or "")
    if not session:
        return "no tmux session is recorded for it"

    planned = launch.launch(row, config, text)
    if planned is None:
        return "no working directory or resume command is recorded for it"

    opened = _tmux(
        row,
        "new-window",
        "-d",
        "-t",
        f"={session}:",
        "-c",
        planned.cwd,
        *window.environment_args(planned.environment),
        "-P",
        "-F",
        "#{pane_id}",
    )
    pane = opened.stdout.strip()
    if opened.returncode != 0 or not pane:
        return f"could not open a window in tmux session {session}"

    typed = _tmux(row, "send-keys", "-t", pane, planned.line, "Enter")
    return "" if typed.returncode == 0 else f"could not type the resume into pane {pane}"


def prompt(row: db.Notification, config: Config, text: str = wake.PROMPT) -> str:
    """Type *text* into *row*'s idle harness and submit it. Returns why not, or ""."""
    pane = _pane(row)
    if not pane:
        return "its tmux pane could not be found"

    if not ready_for_input(_tmux(row, "capture-pane", "-p", "-t", pane).stdout):
        return (
            f"pane {pane} doesn't show an empty prompt, so typing could answer a dialog or a draft"
        )

    if _tmux(row, "send-keys", "-t", pane, "-l", text).returncode != 0:
        return f"could not type into pane {pane}"

    time.sleep(_SUBMIT_PAUSE_SECONDS)
    backend = config.backends.get(row.channel.partition(":")[0], BackendConfig())
    key = submit.key_args(backend.submit_key)
    return (
        ""
        if _tmux(row, "send-keys", "-t", pane, *key).returncode == 0
        else f"could not submit in pane {pane}"
    )
