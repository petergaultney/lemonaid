"""A lemon's page in the web grove: its brief, its conversation, and a box to talk to it.

Typed text goes in through the lemon's front end (`FrontEnd.prompt`), which its harness records
as its user's words. Where the front end can't type, the text goes as mail, which the lemon
reads as a message rather than as its user.
"""

import getpass
import os
from pathlib import Path

from ... import brief, conversation, front_end
from ...config import Config
from ...front_end import chat, interface, pick
from ...inbox import db
from ...messages import tell_delivery
from ...openclaw import sessions

LIMIT = 200  # messages a page shows, with the tool calls among them
MAIL = "mail"

_HOW = {
    "tmux": "Types into its tmux pane as you.",
    "wezterm": "Types into its WezTerm pane as you.",
    "openclaw-chat": "Sends through OpenClaw chat as you.",
    MAIL: "Sends mail, which it reads as a message, not as you.",
}


def _front_end(row: db.Notification) -> tuple[str, interface.FrontEnd | None]:
    name = front_end.location.of(row.metadata, row.switch_source).front_end
    return name, pick.named(name)


def _conversation(row: db.Notification) -> list[conversation.entry.Entry]:
    """Raises OSError when the harness's record can't be read."""
    if row.channel.startswith(sessions.PREFIX):
        return conversation.openclaw.read(sessions.session_key(row.channel), sessions.cli(), LIMIT)

    if row.channel.startswith("claude:"):
        return conversation.claude.read(Path(str(row.metadata.get("transcript_path") or "")), LIMIT)

    if row.channel.startswith("codex:"):
        return conversation.codex.read(Path(str(row.metadata.get("session_path") or "")), LIMIT)

    raise OSError(f"lemonaid can't read a conversation on {row.channel}")


def _brief(channel: str) -> tuple[str, str]:
    """(path, text) of the brief attached to *channel*, or ("", "")."""
    with db.connect() as conn:
        path = brief.attached.by_channel(conn, [channel]).get(channel)
    if path is None:
        return "", ""

    try:
        return str(path), path.read_text()
    except OSError:
        return str(path), ""


def view(channel: str) -> dict:
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    if row is None:
        return {"error": f"No live lemon on {channel}"}

    name, found = _front_end(row)
    how = name if found and found.prompt else MAIL
    path, text = _brief(channel)
    try:
        entries, problem = _conversation(row), ""
    except OSError as error:
        entries, problem = [], str(error)

    return {
        "channel": channel,
        "name": row.name or channel,
        "brief_path": path,
        "brief": text,
        "entries": [entry._asdict() for entry in entries],
        "conversation_problem": problem,
        "how": how,
        "how_text": _HOW.get(how, f"Types into its {how} terminal as you."),
        "room": chat.room_url(str(row.metadata.get("session_key") or "")),
    }


def _mail(channel: str, text: str) -> str:
    sender = f"{os.environ.get('USER') or getpass.getuser()} (web grove)"
    try:
        with db.connect() as conn:
            to = tell_delivery.resolve(conn, channel)
        delivered = tell_delivery.deliver(to, text, sender, wake_it=False)
    except (LookupError, ValueError) as error:
        return str(error)

    return "" if delivered.will_read else delivered.line or "queued, but it may not read it soon"


def say(channel: str, text: str, config: Config) -> str:
    """Put *text* into the lemon on *channel*, as mail only where its front end can't type.
    Returns why it couldn't, or ""."""
    if not text.strip():
        return "nothing to send"

    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    if row is None:
        return f"No live lemon on {channel}"

    _, found = _front_end(row)
    if not (found and found.prompt):
        return _mail(channel, text)

    return found.prompt(row, config, text)
