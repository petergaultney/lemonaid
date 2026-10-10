"""Bring back, through tmux, a lemon that won't read the message it was just sent.

Every command goes to the tmux server the lemon was recorded on: pane ids are
per server, so `%3` on the sender's server is some other pane.
"""

import re
import shlex
import subprocess
import time

from ..config import BackendConfig, Config
from ..inbox import db
from ..launch import window
from ..restore import launch
from ..resume import build_resume_command
from ..tmux import navigation, submit

PROMPT = (
    "You were resumed to read a message: run `lemonaid inbox next --self`. Then rearm "
    "the waiters your brief lists under ## Waiters, and carry on."
)
_SUBMIT_PAUSE_SECONDS = 1.0  # lets the composer take the typed text before Enter
# Claude Code's composer marker, U+276F; a dialog marks its chosen option with it too, then text.
_EMPTY_COMPOSER = re.compile("\\s*\u276f\\s*")


def resume_line(row: db.Notification, config: Config) -> str:
    """The shell line that resumes *row*'s session by hand, or ""."""
    resumable = build_resume_command(config, row.channel, row.metadata)
    if resumable is None:
        return ""

    cwd, argv = resumable
    return f"cd {shlex.quote(cwd)} && {shlex.join(argv)}"


def _tmux(row: db.Notification, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*navigation.server_args(row.metadata.get("tmux_socket")), *args],
        capture_output=True,
        text=True,
    )


def _pane(row: db.Notification) -> str:
    tty = str(row.metadata.get("tty") or "")
    if not tty:
        return ""

    try:
        _, pane = navigation.get_pane_for_tty(tty, row.metadata.get("tmux_socket"))
    except navigation.TmuxUnavailable:
        return ""

    return pane or ""


def ready_for_input(screen: str) -> bool:
    """Whether *screen* shows an empty composer and no dialog."""
    return not window.dialog_in(screen) and any(
        _EMPTY_COMPOSER.fullmatch(line) for line in screen.splitlines()
    )


def start(row: db.Notification, config: Config) -> str:
    """Resume *row*'s exited harness in a new window of its tmux session. Returns why not, or ""."""
    session = str(row.metadata.get("tmux_session") or "")
    if not session:
        return "no tmux session is recorded for it"

    planned = launch.launch(row, config, PROMPT)
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


def prompt(row: db.Notification, config: Config) -> str:
    """Type the wake prompt into *row*'s idle harness. Returns why not, or ""."""
    pane = _pane(row)
    if not pane:
        return "its tmux pane could not be found"

    if not ready_for_input(_tmux(row, "capture-pane", "-p", "-t", pane).stdout):
        return (
            f"pane {pane} doesn't show an empty prompt, so typing could answer a dialog or a draft"
        )

    if _tmux(row, "send-keys", "-t", pane, "-l", PROMPT).returncode != 0:
        return f"could not type into pane {pane}"

    time.sleep(_SUBMIT_PAUSE_SECONDS)
    backend = config.backends.get(row.channel.partition(":")[0], BackendConfig())
    key = submit.key_args(backend.submit_key)
    return (
        ""
        if _tmux(row, "send-keys", "-t", pane, *key).returncode == 0
        else f"could not submit in pane {pane}"
    )
