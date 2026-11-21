"""How a followed conversation's new messages read in a lemon's wake text: author, time,
permalink and text, with Slack's markup as a reader sees it.
"""

import html
import json
import re
import time
from collections import abc
from pathlib import Path

from ..watch import cursors
from . import api, permalink, session, wakes

_MENTION = re.compile(r"<([@#!])([^>|]+)(?:\|([^>]*))?>")
_LINK = re.compile(r"<(https?://[^>|]+)(?:\|([^>]*))?>")


def _names_path() -> Path:
    return wakes.state_dir() / "names.json"


def namer(current: session.Session) -> abc.Callable[[str], str]:
    """A user's display name by ID, from a file kept across runs, else from `users.info`."""
    try:
        known: dict[str, str] = json.loads(_names_path().read_text())
    except (OSError, ValueError):
        known = {}

    def name(user: str) -> str:
        if user not in known:
            try:
                profile = api.call(current, "users.info", user=user)["user"]
            except (api.Failed, api.Unavailable, KeyError):
                return user

            details = profile.get("profile") or {}
            known[user] = (
                details.get("display_name")
                or details.get("real_name")
                or profile.get("name")
                or user
            )
            cursors.write_json(_names_path(), known)
        return known[user]

    return name


def plain(message: dict, name: abc.Callable[[str], str]) -> str:
    """The message's text as a reader sees it: names for mentions, link labels with their URLs."""

    def mention(found: re.Match) -> str:
        sigil, target, label = found.groups()
        if sigil == "@":
            return f"@{label or name(target)}"
        if sigil == "#":
            return f"#{label or target}"
        return f"@{label or target}"  # <!here>, <!channel>

    text = _LINK.sub(lambda m: f"{m[2]} ({m[1]})" if m[2] else m[1], message.get("text") or "")
    return html.unescape(_MENTION.sub(mention, text))


def _author(message: dict, name: abc.Callable[[str], str]) -> str:
    if user := message.get("user"):
        return name(user)

    return message.get("username") or (message.get("bot_profile") or {}).get("name") or "a bot"


def _when(ts: str) -> str:
    moment = time.localtime(float(ts))
    same_day = time.strftime("%Y-%m-%d", moment) == time.strftime("%Y-%m-%d")
    return time.strftime("%H:%M" if same_day else "%Y-%m-%d %H:%M", moment)


def _message(
    conversation: permalink.Conversation, message: dict, name: abc.Callable[[str], str]
) -> abc.Iterator[str]:
    link = permalink.message_link(conversation, message["ts"], message.get("thread_ts", ""))
    yield f"- {_author(message, name)} at {_when(message['ts'])}: {link}"
    text = plain(message, name).strip() or "(no text)"
    yield from (f"  > {line}" for line in text.splitlines())


def _nouns(conversation: permalink.Conversation) -> tuple[str, str]:
    return ("reply", "replies") if conversation.ts else ("message", "messages")


def label(
    conversation: permalink.Conversation,
    messages: abc.Sequence[dict],
    name: abc.Callable[[str], str],
) -> str:
    one, many = _nouns(conversation)
    if len(messages) == 1:
        return f"Slack {one} from {_author(messages[0], name)}"

    return f"{len(messages)} Slack {many}"


def describe(
    conversation: permalink.Conversation,
    messages: abc.Sequence[dict],
    name: abc.Callable[[str], str],
    match: str,
) -> str:
    """*match*, when not "", is the pattern the messages were chosen by."""
    one, many = _nouns(conversation)
    count = f"{len(messages)} new {one if len(messages) == 1 else many}"
    matching = f" matching {match!r}" if match else ""
    return "\n".join(
        [
            f"Slack {conversation.noun} {conversation.link}: {count}{matching}",
            *(line for message in messages for line in _message(conversation, message, name)),
        ]
    )
