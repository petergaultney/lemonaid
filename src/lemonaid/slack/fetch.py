"""The messages a followed conversation has after a cursor: a thread's replies, read with
`conversations.replies`, or a channel's own messages, read with `conversations.history`.

A channel's messages leave out replies in its threads, except those also sent to the channel.
"""

import time
import typing as ty
from collections import abc

from . import api, permalink, session

_PAGE = "200"
_NOISE = frozenset({"channel_join", "channel_leave"})


class Fetched(ty.NamedTuple):
    latest: str  # the conversation's newest message's ts, for its quiet check
    cursor: str  # the newest message read, reported or not; where the next fetch starts
    messages: list[dict]  # to report, oldest first


def _pages(current: session.Session, method: str, **params: str) -> abc.Iterator[dict]:
    page = ""
    while True:
        body = api.call(
            current, method, limit=_PAGE, **params, **({"cursor": page} if page else {})
        )
        yield body
        page = (body.get("response_metadata") or {}).get("next_cursor", "")
        if not body.get("has_more") or not page:
            return


def _newer(messages: abc.Iterable[dict], cursor: str) -> list[dict]:
    after = permalink.order(cursor)
    found = [m for m in messages if permalink.order(m.get("ts", "")) > after]
    return sorted(found, key=lambda m: permalink.order(m["ts"]))


def _replies(current: session.Session, thread: permalink.Conversation, cursor: str) -> Fetched:
    bodies = list(
        _pages(
            current,
            "conversations.replies",
            channel=thread.channel,
            ts=thread.ts,
            oldest=cursor,
            inclusive="false",
        )
    )
    messages = [m for body in bodies for m in body.get("messages") or []]
    roots = [m.get("latest_reply") or "" for m in messages if m.get("ts") == thread.ts]
    replies = _newer((m for m in messages if m.get("ts") != thread.ts), cursor)
    read = replies[-1]["ts"] if replies else cursor
    return Fetched(max([thread.ts, read, *roots], key=permalink.order), read, replies)


def _history(current: session.Session, channel: permalink.Conversation, cursor: str) -> Fetched:
    messages = _newer(
        (
            m
            for body in _pages(
                current,
                "conversations.history",
                channel=channel.channel,
                oldest=cursor,
                inclusive="false",
            )
            for m in body.get("messages") or []
        ),
        cursor,
    )
    read = messages[-1]["ts"] if messages else cursor
    return Fetched(read, read, [m for m in messages if m.get("subtype") not in _NOISE])


def after(current: session.Session, conversation: permalink.Conversation, cursor: str) -> Fetched:
    """Every message newer than *cursor*, paging through Slack's answers."""
    return (_replies if conversation.ts else _history)(current, conversation, cursor)


def latest(current: session.Session, conversation: permalink.Conversation) -> str:
    """The ts a first fetch starts from: the thread's last reply (its root's when it has none),
    or the channel's last message (now, when it has none)."""
    if conversation.ts:
        body = api.call(
            current,
            "conversations.replies",
            channel=conversation.channel,
            ts=conversation.ts,
            limit="1",
        )
        roots = [m for m in body.get("messages") or [] if m.get("ts") == conversation.ts]
        return (roots[0].get("latest_reply") if roots else "") or conversation.ts

    body = api.call(current, "conversations.history", channel=conversation.channel, limit="1")
    newest = [m["ts"] for m in body.get("messages") or [] if m.get("ts")]
    return max(newest, key=permalink.order) if newest else f"{time.time():.6f}"
