"""Follow one Slack thread or channel for one lemon: what a `poll` answers, from the lemon's
cursor (docs/source-plugins.md).

A first poll takes the conversation as seen, unless the subscription's `--after` names where
to start. With a `--match`, only messages whose text it matches are reported; the cursor
passes the rest. lemonaid polls again when the gateway signals the conversation (`serve`
turns that into a `ready` notice), and after `every`: `_BACKSTOP` while a socket is up, for
what it does not report (a channel the user has not joined), else `fetch_every`.

The subscription ends when the lemon's brief is done or the conversation has had no message
for `QUIET_DAYS`.
"""

import argparse
import json
import logging
import re
import time
import typing as ty
from collections import abc

from . import api, fetch, permalink, session, signed_out, wake_text, wakes
from .config import SlackConfig

QUIET_DAYS = 7
_BACKSTOP = 600.0

_log = logging.getLogger("lemonaid_slack.follow")


class Usage(ValueError):
    pass


class Subscription(ty.NamedTuple):
    conversation: permalink.Conversation
    after: str  # where a first fetch starts; "" for the newest message
    match: str  # a regex choosing the messages reported; "" reports all


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> ty.NoReturn:
        raise Usage(message)


def _conversation(value: str) -> permalink.Conversation:
    try:
        return permalink.parse(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def _pattern(value: str) -> str:
    try:
        re.compile(value)
    except re.error as error:
        raise argparse.ArgumentTypeError(f"not a regex: {value!r}: {error}") from None
    return value


def _ts(value: str) -> str:
    if value and not permalink.is_ts(value):
        raise argparse.ArgumentTypeError(
            f"not a Slack message ts such as 1794857970.806329: {value!r}"
        )
    return value


def parse(args: abc.Sequence[str]) -> Subscription:
    """The subscription `lemonaid watch slack <args>` names, or Usage."""
    parser = _Parser(prog="lemonaid watch slack", add_help=False)
    parser.add_argument("link", type=_conversation)
    parser.add_argument("--after", type=_ts, default="")
    parser.add_argument("--match", type=_pattern, default="")
    found = parser.parse_args(list(args))
    return Subscription(found.link, found.after, found.match)


def _quiet(latest: str) -> bool:
    return time.time() - float(latest) >= QUIET_DAYS * 86400


def _every(settings: SlackConfig) -> str:
    return f"every {_BACKSTOP if wakes.gateway_up() else settings.fetch_every:g}"


def _ended(conversation: permalink.Conversation, reason: str) -> list[str]:
    noun, link = conversation.noun, conversation.link
    return [
        f"end Stopped following Slack {noun} {link}: {reason}",
        f"label stopped following a Slack {noun}",
    ]


def _wake(sub: Subscription, current: session.Session, messages: abc.Sequence[dict]) -> list[str]:
    name = wake_text.namer(current)
    wanted = re.compile(sub.match) if sub.match else None
    chosen = [m for m in messages if wanted is None or wanted.search(wake_text.plain(m, name))]
    if not chosen:
        return []

    text = wake_text.describe(sub.conversation, chosen, name, sub.match)
    return [
        "wake",
        f"label {wake_text.label(sub.conversation, chosen, name)}",
        f"count {len(chosen)}",
        *(f"text {line}" for line in text.split("\n")),
    ]


def _signed_out(current: session.Session | None, settings: SlackConfig) -> list[str]:
    return [
        f"problem {signed_out.lemon_problem(current)}",
        "label Slack sign-in needed",
        f"every {settings.fetch_every:g}",
    ]


def _read(sub: Subscription, current: session.Session, saved: dict | None) -> list[str]:
    if saved is None and not sub.after:
        start = fetch.latest(current, sub.conversation)
        saved, found = {"cursor": start, "latest": start}, fetch.Fetched(start, start, [])
    else:
        saved = saved or {"cursor": sub.after, "latest": sub.after}
        found = fetch.after(current, sub.conversation, saved["cursor"])
    latest = max(saved["latest"], found.latest, key=permalink.order)
    return [
        *_wake(sub, current, found.messages),
        f"cursor {json.dumps({'cursor': found.cursor, 'latest': latest})}",
        *(_ended(sub.conversation, f"nothing new in {QUIET_DAYS} days") if _quiet(latest) else ()),
    ]


def answer(
    sub: Subscription,
    follower: str,
    saved: dict | None,
    done: bool,
    settings: SlackConfig,
) -> list[str]:
    """The lines of a `poll`'s answer. *saved* is the lemon's cursor, None before its first."""
    if done:
        return _ended(sub.conversation, "your brief is done")

    wakes.follow(sub.conversation.channel, sub.conversation.ts, follower)
    if saved is not None and _quiet(saved["latest"]):
        return _ended(sub.conversation, f"nothing new in {QUIET_DAYS} days")

    current = session.load()
    if signed_out.problem(current):
        if current is None:
            signed_out.mark(None)
        return _signed_out(current, settings)

    assert current is not None  # problem() names a missing session
    try:
        return [*_read(sub, current, saved), _every(settings)]
    except api.Expired:
        signed_out.mark(current)
        return _signed_out(current, settings)
    except api.Unavailable as error:
        conversation = sub.conversation
        _log.info("cannot read Slack %s %s now: %s", conversation.noun, conversation.link, error)
        return [f"every {settings.fetch_every:g}"]
