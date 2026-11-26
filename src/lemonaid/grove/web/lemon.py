"""A lemon's page in the web grove: its brief, its conversation, and a box to talk to it.

Typed text goes in through the lemon's front end (`FrontEnd.prompt`), which its harness records
as its user's words. Where the front end can't type, the text goes as mail, which the lemon
reads as a message rather than as its user.
"""

import getpass
import os
import time
from pathlib import Path

from ... import conversation, front_end
from ...brief import attached, family, pr, render, target
from ...config import Config
from ...front_end import chat, interface, pick
from ...inbox import db
from ...messages import tell_delivery
from ...openclaw import sessions
from . import brief_page

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


def _named(session_key: str) -> str:
    """The name of the lemon on another OpenClaw session."""
    with db.connect() as conn:
        row = db.get_by_channel(conn, sessions.channel(session_key), unread_only=False)
    return (row.name if row else "") or "the session that started it"


def _conversation(row: db.Notification) -> list[conversation.entry.Entry]:
    """Raises OSError when the harness's record can't be read."""
    if row.channel.startswith(sessions.PREFIX):
        return conversation.openclaw.read(
            sessions.session_key(row.channel), sessions.cli(), LIMIT, _named
        )

    if row.channel.startswith("claude:"):
        return conversation.claude.read(Path(str(row.metadata.get("transcript_path") or "")), LIMIT)

    if row.channel.startswith("codex:"):
        return conversation.codex.read(Path(str(row.metadata.get("session_path") or "")), LIMIT)

    raise OSError(f"lemonaid can't read a conversation on {row.channel}")


def _brief(row: db.Notification, config: Config, prs: pr.Lookup, width: int) -> tuple[str, dict]:
    """(path, parts) of *row*'s brief as the inbox's brief pane draws it (`brief_page`), or
    ("", {}) without one."""
    with db.connect() as conn:
        found = attached.by_channel(conn, [row.channel])
    path = found.get(row.channel)
    if path is None:
        return "", {}

    now = time.time()
    shown = family.added(
        render.view(
            target.for_notification(row, found),
            now,
            prs,
            config.places.roots,
            config.brief.vaults,
            render.SummaryPolicy(config.brief.summary_open, config.brief.summary_long),
        )
    )
    return str(path), brief_page.drawn(shown, now, config.brief.vaults, width)


def view(channel: str, config: Config, prs: pr.Lookup, width: int = brief_page.WIDTH) -> dict:
    """Everything but the conversation, which is slower to read (`talk`), with the brief drawn
    *width* characters wide. *prs* answers a PR's state, as a `pr.Cache` does without waiting."""
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    if row is None:
        return {"error": f"No live lemon on {channel}"}

    name, found = _front_end(row)
    how = name if found and found.prompt else MAIL
    path, brief = _brief(row, config, prs, max(30, min(200, width)))
    return {
        "channel": channel,
        "name": row.name or channel,
        "brief_path": path,
        "brief": brief,
        "how": how,
        "how_text": _HOW.get(how, f"Types into its {how} terminal as you."),
        "room": chat.room_url(str(row.metadata.get("session_key") or "")),
    }


def talk(channel: str) -> dict:
    """The lemon's conversation, or why it can't be read."""
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    if row is None:
        return {"error": f"No live lemon on {channel}"}

    try:
        entries, problem = _conversation(row), ""
    except OSError as error:
        entries, problem = [], str(error)
    return {"entries": [entry._asdict() for entry in entries], "conversation_problem": problem}


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
