"""A lemon's page in the web grove: its brief, its conversation, and a box to talk to it.

Typed text goes in through the lemon's front end (`FrontEnd.prompt`), which its harness records
as its user's words. Where the front end can't type, the text goes as mail, which the lemon
reads as a message rather than as its user.
"""

import getpass
import os
import time
from collections import abc
from pathlib import Path

from ... import conversation, front_end, openclaw
from ...brief import attached, family, identity, pr, render, target
from ...config import Config
from ...front_end import chat, interface, pick
from ...inbox import db, pins, turns
from ...messages import tell_delivery
from ...openclaw import gateway, sessions
from . import attachments, brief_page

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


def _transcript(row: db.Notification) -> Path:
    return Path(str(row.metadata.get("transcript_path") or row.metadata.get("session_path") or ""))


def _mark(row: db.Notification) -> str:
    """What changes whenever the lemon's conversation does, much cheaper to learn than the
    conversation. Raises OSError when it can't be learned."""
    if row.channel.startswith(sessions.PREFIX):
        key = sessions.session_key(row.channel)
        failed = openclaw.turns.failed(key)
        return (
            f"{conversation.openclaw.mark(key, sessions.cli())}:{failed[-1].at_ms if failed else 0}"
        )

    found = _transcript(row).stat()
    return f"{found.st_mtime_ns}:{found.st_size}"


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


def _brief(
    row: db.Notification, config: Config, prs: pr.Lookup, width: int
) -> tuple[str, dict, render.Section | None]:
    """(path, parts, its lemon's section) of *row*'s brief as the inbox's brief pane draws it
    (`brief_page`), or ("", {}, None) without one."""
    with db.connect() as conn:
        found = attached.by_channel(conn, [row.channel])
    path = found.get(row.channel)
    if path is None:
        return "", {}, None

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
    own = shown.sections[0] if shown.sections else None
    return str(path), brief_page.drawn(shown, now, config.brief.vaults, width), own


def view(channel: str, config: Config, prs: pr.Lookup, width: int = brief_page.WIDTH) -> dict:
    """Everything but the conversation, which is slower to read (`talk`), with the brief drawn
    *width* characters wide. *prs* answers a PR's state, as a `pr.Cache` does without waiting."""
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
        pinned = pins.is_pinned(conn, channel)
    if row is None:
        return {"error": f"No live lemon on {channel}"}

    name, found = _front_end(row)
    how = name if found and found.prompt else MAIL
    path, brief, own = _brief(row, config, prs, max(30, min(200, width)))
    return {
        "channel": channel,
        "name": row.name or channel,
        "brief_path": path,
        "status": own.state if own else "",
        "brief_id": identity.brief_name(own.lemon_id) if own and own.lemon_id else "",
        "pinned": pinned,
        "working": turns.mid_turn(row, time.time()),
        "brief": brief,
        "how": how,
        "how_text": _HOW.get(how, f"Types into its {how} terminal as you."),
        "attach": name != chat.NAME or gateway.held(),  # an OpenClaw lemon's files need a held one
    }


def mark(channel: str) -> str:
    """What changes whenever the lemon's page would: its conversation, its brief's file, or
    whether it is mid-turn."""
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
        brief = attached.by_channel(conn, [channel]).get(channel)
    if row is None:
        return "gone"

    try:
        talked = _mark(row)
    except OSError as error:
        talked = str(error)
    try:
        written = brief.stat().st_mtime_ns if brief else 0
    except OSError:
        written = 0
    return f"{talked}|{written}|{turns.mid_turn(row, time.time())}"


_read: dict[str, tuple[str, list[conversation.entry.Entry]]] = {}  # by channel, with its mark


def _unless_unchanged(row: db.Notification) -> list[conversation.entry.Entry]:
    """The conversation as last read while its mark is the same: a page asks every few seconds,
    and a busy OpenClaw session's conversation is megabytes to read back."""
    try:
        now = _mark(row)
    except OSError:
        return _conversation(row)

    kept = _read.get(row.channel)
    if kept and kept[0] == now:
        return kept[1]

    entries = _conversation(row)
    _read[row.channel] = (now, entries)
    return entries


def talk(channel: str) -> dict:
    """The lemon's conversation, or why it can't be read."""
    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    if row is None:
        return {"error": f"No live lemon on {channel}"}

    try:
        entries, problem = _unless_unchanged(row), ""
        if row.channel.startswith(sessions.PREFIX):
            entries = conversation.openclaw.with_failures(
                entries, sessions.session_key(row.channel)
            )
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


def say(channel: str, text: str, config: Config, attached: abc.Sequence[str] = ()) -> str:
    """Put *text* and the files *attached* names (`attachments`) into the lemon on *channel*, as
    mail only where its front end can't type. An OpenClaw session gets the files themselves;
    any other lemon, their paths on this machine. Returns why it couldn't, or ""."""
    files = attachments.found(attached)
    if isinstance(files, str):
        return files

    if not text.strip() and not files:
        return "nothing to send"

    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    if row is None:
        return f"No live lemon on {channel}"

    name, found = _front_end(row)
    if not (found and found.prompt):
        return _mail(channel, attachments.as_text(text, files))

    key = sessions.session_key(row.channel)
    if files and name == chat.NAME and key:
        problem = chat.send(key, text, attachments.for_chat(files))
    else:
        problem = found.prompt(row, config, attachments.as_text(text, files))
    if not problem:  # answering it read it, and an unread lemon never shows mid-turn
        with db.connect() as conn:
            db.mark_all_read_for_channel(conn, channel)
    return problem
