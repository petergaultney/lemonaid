"""Bring back, through WezTerm, a lemon that won't read the message it was just sent.

Every command goes to the WezTerm instance the lemon was recorded in: pane ids
are per instance. Spawning into a workspace that no longer exists recreates it,
so a toss needs nothing more than a resume here.
"""

import time
import typing as ty

from ..config import BackendConfig, Config
from ..inbox import db
from ..lemon_watchers import owners
from ..restore import launch
from ..wezterm import client, spawn
from . import autoresume_tmux, wake

_SUBMIT_PAUSE_SECONDS = 1.0  # lets the composer take the typed text before submitting
_SUBMIT = {"Enter": "\r", "C-Enter": "\x1b[13;5u"}  # the bytes tmux's submit keys send


def _socket(row: db.Notification) -> str | None:
    return row.metadata.get("wezterm_socket") or None


def _window(workspace: str, panes: ty.Iterable[dict[str, ty.Any]]) -> int | None:
    return next((p["window_id"] for p in panes if p.get("workspace") == workspace), None)


def _spawn_args(
    workspace: str, window: int | None, cwd: str, environment: dict[str, str]
) -> list[str]:
    where = ["--window-id", str(window)] if window is not None else ["--new-window"]
    workspace_args = [] if window is not None else ["--workspace", workspace]
    return spawn.spawn_args([*where, *workspace_args], cwd, environment)


def start(row: db.Notification, config: Config, text: str = wake.PROMPT) -> str:
    """Resume *row*'s exited harness on *text* in a new tab of its workspace. Returns why not, or ""."""
    workspace = str(row.metadata.get("wezterm_workspace") or "")
    if not workspace:
        return "no WezTerm workspace is recorded for it"

    planned = launch.launch(row, config, text)
    if planned is None:
        return "no working directory or resume command is recorded for it"

    panes = client.panes(_socket(row))
    if panes is None:
        return "WezTerm could not list its panes"

    opened = client.run(
        _spawn_args(workspace, _window(workspace, panes), planned.cwd, planned.environment),
        _socket(row),
    )
    pane = opened.stdout.strip()
    if opened.returncode != 0 or not pane.isdigit():
        return f"could not open a tab in WezTerm workspace {workspace}"

    if spawn.type_line(pane, planned.line, _socket(row)):
        return f"could not type the resume into pane {pane}"

    return ""


def _pane(row: db.Notification) -> str:
    tty = str(row.metadata.get("tty") or "")
    found = next(
        (p for p in client.panes(_socket(row)) or [] if tty and p.get("tty_name") == tty), None
    )
    return str(found["pane_id"]) if found else ""


def prompt(row: db.Notification, config: Config, text: str = wake.PROMPT) -> str:
    """Type *text* into *row*'s idle harness and submit it. Returns why not, or ""."""
    pane = _pane(row)
    if not pane:
        return "its WezTerm pane could not be found"

    # A harness on a reused tty can be another lemon, which would take the prompt as its own.
    match owners.on_recorded_tty(row, owners.running()):
        case False:
            return "its recorded terminal runs another lemon now, not this one"
        case None:
            return "lemonaid couldn't confirm which lemon runs in its recorded terminal"

    screen = client.run(["get-text", "--pane-id", pane], _socket(row))
    if screen.returncode != 0 or not autoresume_tmux.ready_for_input(screen.stdout):
        return (
            f"pane {pane} doesn't show an empty prompt, so typing could answer a dialog or a draft"
        )

    if client.run(["send-text", "--no-paste", "--pane-id", pane, text], _socket(row)).returncode:
        return f"could not type into pane {pane}"

    time.sleep(_SUBMIT_PAUSE_SECONDS)
    backend = config.backends.get(row.channel.partition(":")[0], BackendConfig())
    submitted = client.run(
        ["send-text", "--no-paste", "--pane-id", pane, _SUBMIT[backend.submit_key]], _socket(row)
    )
    return "" if submitted.returncode == 0 else f"could not submit in pane {pane}"
