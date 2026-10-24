"""Fast tmux popups: an app that keeps running in a hidden session, shown in a popup at once.

Starting Python and Textual for every popup is too slow to feel like a modal, so the app runs
all the time in a hidden session, `_lma_<name>`, as the inbox's scratch pane does in
`_lma_scratch`. A popup over the client, a few cells in from each edge (`popup_margin`),
attaches to that session, so it shows what the app has already drawn; the app hides it again
by detaching the popup's client. The client that opened it is kept in a session option for the
app to read.

The app is found by name: popup `grove` runs the module `lemonaid.grove.popup_app`, whose
`run(opener, rename_session, hide)` the resident calls (see `popup_resident`). Nothing here
knows any app.
"""

import importlib.metadata
import json
import os
import subprocess
import sys

from ..log import get_logger
from . import popup_guard
from .command import run

SETTINGS_OPTION = "@lemonaid_popup_settings"  # the build and overrides the resident started with
OPENER_OPTION = "@lemonaid_popup_client"  # the client the popup was last opened over
_TIMEOUT_SECONDS = 2.0
# What says which inbox, layout and config a lemonaid process uses. tmux starts the resident
# with the server's environment, so these are passed to it explicitly.
_CARRIED = (
    "LEMONAID_DB",
    "LEMONAID_STATE_DIR",
    "LEMONAID_CONFIG",
    "LEMONAID_BRIEFS_DIR",
    "LEMONAID_LEMONS_DIR",
    "LEMONAID_LEGACY_BRIEFS_DIR",
    "LEMONAID_LOG",
    "LEMONAID_DEBUG",
)
# How long Textual waits after Escape for the rest of a key sequence. tmux sends a sequence
# whole, so a short wait is safe, and Escape then feels immediate.
_ESCAPE_DELAY_MS = 25
_log = get_logger("tmux.fast_popup")


def module_for(name: str) -> str:
    """The module that holds popup *name*'s app."""
    return f"lemonaid.{name}.popup_app"


def session_for(name: str) -> str:
    return f"_lma_{name}"


def _tmux(*args: str) -> subprocess.CompletedProcess[str]:
    return run(list(args), timeout=_TIMEOUT_SECONDS)


def _client() -> tuple[str, str, int, int] | None:
    # The session goes last, split off whole: tmux names can't hold a colon but can hold spaces.
    found = _tmux(
        "display-message", "-p", "#{client_name}:#{client_width}:#{client_height}:#{client_session}"
    )
    try:
        name, width, height, session = found.stdout.rstrip("\n").split(":", 3)
        return name, session, int(width), int(height)
    except ValueError:
        _log.warning(
            "no popup: tmux described the client as %r (%s)",
            found.stdout,
            found.stderr.strip(),
        )
        return None


def settings() -> dict[str, str]:
    """The lemonaid settings in this environment, which the resident must share."""
    return {key: os.environ[key] for key in _CARRIED if key in os.environ}


def stamp(settings: dict[str, str]) -> str:
    """What a resident is reused for: these settings and this build, so an install replaces it."""
    build = importlib.metadata.version("lemonaid-inbox")
    return json.dumps({"build": build, "settings": settings}, sort_keys=True)


def _start(name: str, settings: dict[str, str], width: int, height: int) -> None:
    session = session_for(name)
    _tmux(
        "new-session",
        "-d",
        "-s",
        session,
        "-x",
        str(width),
        "-y",
        str(height),
        *(arg for key, value in settings.items() for arg in ("-e", f"{key}={value}")),
        "-e",
        f"ESCDELAY={_ESCAPE_DELAY_MS}",
        # The tmux server's own values for settings the caller left unset don't apply.
        "env",
        *(arg for key in _CARRIED if key not in settings for arg in ("-u", key)),
        sys.executable,
        "-m",
        "lemonaid.cli",
        "tmux",
        "popup-serve",
        name,
    )
    _tmux("set-option", "-t", session, "status", "off")
    _tmux("set-option", "-t", session, SETTINGS_OPTION, stamp(settings))
    for hook, command in popup_guard.hooks(session, OPENER_OPTION).items():
        _tmux("set-hook", "-g", hook, command)


def _running(name: str, settings: dict[str, str]) -> bool:
    """Whether popup *name*'s resident with *settings* and this build is up; one started otherwise
    is stopped.
    """
    session = session_for(name)
    if _tmux("has-session", "-t", f"={session}").returncode != 0:
        return False

    started_with = _tmux("show-option", "-t", f"={session}:", "-qv", SETTINGS_OPTION).stdout.strip()
    if started_with == stamp(settings):
        return True

    _log.info("restarting popup %s, started with %s", name, started_with)
    _tmux("kill-session", "-t", f"={session}")
    return False


def _size(client_width: int, client_height: int, margin: int) -> tuple[int, int]:
    return max(30, client_width - 2 * margin), max(10, client_height - 2 * margin)


def warm(name: str, margin: int) -> None:
    """Start popup *name*'s resident if it isn't up, sized for this client's popup."""
    carried = settings()
    if _running(name, carried):
        return

    client = _client()
    _start(name, carried, *_size(client[2], client[3], margin) if client else (200, 50))


def opener(name: str) -> str:
    """The client popup *name* was last opened over."""
    return _tmux("show-option", "-t", f"={session_for(name)}:", "-qv", OPENER_OPTION).stdout.strip()


def hide(name: str) -> None:
    """Close popup *name* wherever it shows, leaving its app running."""
    _tmux("detach-client", "-s", f"={session_for(name)}")


def attach_command(name: str) -> list[str]:
    """The popup's command: a client of the popup's own tmux server, attached to the resident's
    session. `sh`, whatever the user's shell, and `=` for an exact match, which zsh would expand.
    """
    attach = f'exec env -u TMUX tmux -S "${{TMUX%%,*}}" attach-session -t ={session_for(name)}'
    return ["sh", "-c", attach]


def show(name: str, margin: int, title: str = "") -> None:
    """Open popup *name* over the calling client, *margin* cells in from each edge and titled
    *title*, and return without waiting for it to close; called from inside it, close it.
    """
    client = _client()
    if client is None:
        return

    client_name, session, client_width, client_height = client
    if session == session_for(name):
        hide(name)
        return

    warm(name, margin)
    hide(name)  # one popup at a time, so a choice switches the client it shows on
    width, height = _size(client_width, client_height, margin)
    _tmux("set-option", "-t", f"={session_for(name)}:", OPENER_OPTION, client_name)
    subprocess.Popen(
        [
            "tmux",
            "display-popup",
            "-E",
            "-c",
            client_name,
            "-w",
            str(width),
            "-h",
            str(height),
            "-x",
            str(margin),
            "-y",
            str(client_height - margin),  # its bottom line
            "-S",
            "fg=#f2d94e",
            "-T",
            title or f" {name} ",
            *attach_command(name),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
