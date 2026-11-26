"""A chat room as a front end: the room an OpenClaw gateway serves a lemon's session in.

There is no terminal to find or type into. Showing a lemon opens its room. The gateway runs
its turns (see `openclaw`); prompting one sends the text with `chat.send`, the call OpenClaw's
own chat clients make for what their user types. A command an OpenClaw session runs is "in"
this front end, and `lemon start` from it opens a new session of the same agent.
"""

import uuid
import webbrowser
from collections import abc

from ..config import Config
from ..inbox import db
from ..log import get_logger
from ..openclaw import gateway, sessions
from . import interface

_log = get_logger("front_end.chat")

NAME = "openclaw-chat"
_SEND_TIMEOUT_SECONDS = 60  # the gateway answers once it has started the turn


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


def send(session_key: str, text: str) -> str:
    """Send *text* into a session as its user's. Returns why not, or ""."""
    params = {"sessionKey": session_key, "message": text, "idempotencyKey": str(uuid.uuid4())}
    try:
        gateway.call(sessions.cli(), "chat.send", params, _SEND_TIMEOUT_SECONDS)
    except OSError as error:
        return f"chat.send failed: {error}"

    return ""


def prompt(row: db.Notification, config: Config, text: str) -> str:
    key = sessions.session_key(row.channel)
    return send(key, text) if key else f"{row.channel} is not an OpenClaw session"


def terminal() -> interface.Terminal:
    return interface.Terminal(
        name=NAME,
        workspace_key="",
        here=lambda: sessions.hosted_codex_home() is not None,  # a command the gateway runs
        show=show,
        exists=lambda tty, instance=None, not_after=None: None,
    )
