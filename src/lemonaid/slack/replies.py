"""A thread's replies after a cursor, read with `conversations.replies`, and the wake text that
reports them: author, time, permalink and text.
"""

import html
import json
import re
import time
import typing as ty
from collections import abc
from pathlib import Path

from ..watch import cursors
from . import api, permalink, session, wakes

_PAGE = "200"
_MENTION = re.compile(r"<([@#!])([^>|]+)(?:\|([^>]*))?>")
_LINK = re.compile(r"<(https?://[^>|]+)(?:\|([^>]*))?>")


class Fetched(ty.NamedTuple):
    latest: str  # the thread's last reply's ts, or its root's when it has none
    replies: list[dict]  # after the cursor, oldest first


def after(current: session.Session, thread: permalink.Thread, cursor: str) -> Fetched:
    """Every reply newer than *cursor*, paging through `conversations.replies`."""
    replies: list[dict] = []
    latest, page = thread.ts, ""
    while True:
        body = api.call(
            current,
            "conversations.replies",
            channel=thread.channel,
            ts=thread.ts,
            oldest=cursor,
            inclusive="false",
            limit=_PAGE,
            **({"cursor": page} if page else {}),
        )
        for message in body.get("messages") or []:
            if message.get("ts") == thread.ts:
                latest = max(latest, message.get("latest_reply") or "", key=permalink.order)
            elif permalink.order(message.get("ts", "")) > permalink.order(cursor):
                replies.append(message)
        page = (body.get("response_metadata") or {}).get("next_cursor", "")
        if not body.get("has_more") or not page:
            break
    replies.sort(key=lambda m: permalink.order(m["ts"]))
    latest = max([latest, *(m["ts"] for m in replies)], key=permalink.order)
    return Fetched(latest, replies)


def latest(current: session.Session, thread: permalink.Thread) -> str:
    """The thread's last reply's ts, or its root's when it has none."""
    body = api.call(
        current, "conversations.replies", channel=thread.channel, ts=thread.ts, limit="1"
    )
    roots = [m for m in body.get("messages") or [] if m.get("ts") == thread.ts]
    return (roots[0].get("latest_reply") if roots else "") or thread.ts


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


def _plain(text: str, name: abc.Callable[[str], str]) -> str:
    """Slack's markup as a reader sees it: names for mentions, link labels with their URLs."""

    def mention(found: re.Match) -> str:
        sigil, target, label = found.groups()
        if sigil == "@":
            return f"@{label or name(target)}"
        if sigil == "#":
            return f"#{label or target}"
        return f"@{label or target}"  # <!here>, <!channel>

    text = _LINK.sub(lambda m: f"{m[2]} ({m[1]})" if m[2] else m[1], text)
    return html.unescape(_MENTION.sub(mention, text))


def author(message: dict, name: abc.Callable[[str], str]) -> str:
    if user := message.get("user"):
        return name(user)

    return message.get("username") or (message.get("bot_profile") or {}).get("name") or "a bot"


def _when(ts: str) -> str:
    moment = time.localtime(float(ts))
    same_day = time.strftime("%Y-%m-%d", moment) == time.strftime("%Y-%m-%d")
    return time.strftime("%H:%M" if same_day else "%Y-%m-%d %H:%M", moment)


def _reply(
    thread: permalink.Thread, message: dict, name: abc.Callable[[str], str]
) -> abc.Iterator[str]:
    yield (
        f"- {author(message, name)} at {_when(message['ts'])}: "
        f"{permalink.reply_link(thread, message['ts'])}"
    )
    text = _plain(message.get("text") or "", name).strip() or "(no text)"
    yield from (f"  > {line}" for line in text.splitlines())


def describe(
    thread: permalink.Thread, replies: abc.Sequence[dict], name: abc.Callable[[str], str]
) -> str:
    count = f"{len(replies)} new repl{'y' if len(replies) == 1 else 'ies'}"
    return "\n".join(
        [
            f"Slack thread {thread.link}: {count}",
            *(line for message in replies for line in _reply(thread, message, name)),
        ]
    )
