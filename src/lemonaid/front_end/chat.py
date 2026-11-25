"""A chat room as a front end: the room an OpenClaw gateway serves a lemon's session in.

There is no terminal to find or type into. Showing a lemon opens its room, and lemonaid
never starts or prompts one here: the gateway runs its turns (see `openclaw`).
"""

import webbrowser
from collections import abc

from ..config import Config
from ..log import get_logger
from . import interface

_log = get_logger("front_end.chat")

NAME = "openclaw-chat"


def room_url(session_key: str) -> str:
    """A link to the Matrix room a session key names, or "" for another kind of chat.

    A key reads `agent:<agent>:<chat>:<kind>:<peer>`, and a Matrix room id itself holds a
    colon (`!abc:server`).
    """
    parts = session_key.split(":", 4)
    if len(parts) < 5 or parts[2] != "matrix" or not parts[4].startswith("!"):
        return ""

    return f"https://matrix.to/#/{parts[4]}"


def show(
    metadata: interface.Metadata | None,
    config: Config,
    on_resume: abc.Callable[[str], None] | None = None,
) -> bool:
    url = room_url(str((metadata or {}).get("session_key") or ""))
    if not url:
        return False

    try:
        return webbrowser.open(url)
    except webbrowser.Error as error:
        _log.warning("could not open %s: %s", url, error)
        return False


def terminal() -> interface.Terminal:
    return interface.Terminal(
        name=NAME,
        workspace_key="",
        here=lambda: False,  # nothing runs in a chat room
        show=show,
        exists=lambda tty, instance=None, not_after=None: None,
    )
