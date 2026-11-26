"""A chat room as a front end: the room an OpenClaw gateway serves a lemon's session in.

There is no terminal to find or type into, and nothing to show. The gateway runs
its turns (see `openclaw`); prompting one sends the text with `chat.send`, the call OpenClaw's
own chat clients make for what their user types. A command an OpenClaw session runs is "in"
this front end, and `lemon start` from it opens a new session of the same agent.
"""

import uuid

from ..config import Config
from ..inbox import db
from ..openclaw import gateway, sessions
from . import interface

NAME = "openclaw-chat"
_SEND_TIMEOUT_SECONDS = 60  # the gateway answers once it has started the turn


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
        show=lambda metadata, config, on_resume=None: False,
        exists=lambda tty, instance=None, not_after=None: None,
    )
