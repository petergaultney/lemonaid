"""Slack message permalinks: the thread one names, and the link to a reply in it.

A reply's permalink names its thread in the `thread_ts` query value; without one, the link
is the thread's root message itself.
"""

import decimal
import re
import typing as ty
import urllib.parse

_PATH = re.compile(r"/archives/([A-Z0-9]+)/p(\d{10})(\d{6})")
_TS = re.compile(r"\d{10}\.\d{6}")


class Thread(ty.NamedTuple):
    host: str  # the workspace's, such as acme.slack.com
    channel: str
    ts: str  # the root message's

    @property
    def link(self) -> str:
        return f"https://{self.host}/archives/{self.channel}/p{self.ts.replace('.', '')}"


def is_ts(value: str) -> bool:
    return bool(_TS.fullmatch(value))


def parse(link: str) -> Thread:
    url = urllib.parse.urlparse(link.strip())
    found = _PATH.search(url.path)
    if url.scheme != "https" or not url.hostname or not found:
        raise ValueError(f"not a Slack message permalink: {link}")

    channel, seconds, micros = found.groups()
    thread = urllib.parse.parse_qs(url.query).get("thread_ts", [])
    if thread and not is_ts(thread[0]):
        raise ValueError(f"not a Slack thread_ts: {thread[0]}")

    return Thread(url.hostname, channel, thread[0] if thread else f"{seconds}.{micros}")


def reply_link(thread: Thread, ts: str) -> str:
    query = urllib.parse.urlencode({"thread_ts": thread.ts, "cid": thread.channel})
    return f"https://{thread.host}/archives/{thread.channel}/p{ts.replace('.', '')}?{query}"


def order(ts: str) -> decimal.Decimal:
    """A message ts as a number to compare; a float would round off its microseconds."""
    return decimal.Decimal(ts or "0")
