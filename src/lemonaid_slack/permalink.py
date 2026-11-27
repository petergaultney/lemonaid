"""Slack links: the channel or thread one names, and the link to a message in it.

A channel's link is `/archives/<channel>`. A message's adds `/p<ts>`, and a reply's names its
thread in the `thread_ts` query value; without one, the message is its thread's root.
"""

import decimal
import re
import typing as ty
import urllib.parse

_PATH = re.compile(r"/archives/([A-Z0-9]+)(?:/p(\d{10})(\d{6}))?/?")
_TS = re.compile(r"\d{10}\.\d{6}")


class Conversation(ty.NamedTuple):
    """A channel, or one thread in it."""

    host: str  # the workspace's, such as acme.slack.com
    channel: str
    ts: str  # the thread's root message's; "" for the whole channel

    @property
    def link(self) -> str:
        message = f"/p{self.ts.replace('.', '')}" if self.ts else ""
        return f"https://{self.host}/archives/{self.channel}{message}"

    @property
    def target(self) -> tuple[str, ...]:
        """How a subscription and the wake files name it."""
        return (self.channel, self.ts) if self.ts else (self.channel,)

    @property
    def noun(self) -> str:
        return "thread" if self.ts else "channel"


def is_ts(value: str) -> bool:
    return bool(_TS.fullmatch(value))


def parse(link: str) -> Conversation:
    url = urllib.parse.urlparse(link.strip())
    found = _PATH.fullmatch(url.path)
    if url.scheme != "https" or not url.hostname or not found:
        raise ValueError(f"not a Slack channel or message link: {link}")

    channel, seconds, micros = found.groups()
    thread = urllib.parse.parse_qs(url.query).get("thread_ts", [])
    if thread and not is_ts(thread[0]):
        raise ValueError(f"not a Slack thread_ts: {thread[0]}")

    root = thread[0] if thread else f"{seconds}.{micros}" if seconds else ""
    return Conversation(url.hostname, channel, root)


def message_link(conversation: Conversation, ts: str, thread_ts: str = "") -> str:
    """The permalink of message *ts*; *thread_ts* names the thread of a reply sent to the
    channel as well."""
    base = f"https://{conversation.host}/archives/{conversation.channel}/p{ts.replace('.', '')}"
    thread = conversation.ts or thread_ts
    if not thread or thread == ts:
        return base

    return f"{base}?{urllib.parse.urlencode({'thread_ts': thread, 'cid': conversation.channel})}"


def order(ts: str) -> decimal.Decimal:
    """A message ts as a number to compare; a float would round off its microseconds."""
    return decimal.Decimal(ts or "0")
