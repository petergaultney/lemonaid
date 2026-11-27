"""Which lemons have something new to tell the user between two reads of the grove: those that
went unread, or reported again while still unread. Opening a lemon's page marks it read, so it
notifies again only once it has news after that. A lemon read anywhere, such as in the desktop
inbox, has its notification cleared from the devices it went to."""

import typing as ty
import urllib.parse
from collections import abc

from .... import conversation
from ...model import Lemon


class Event(ty.NamedTuple):
    lemon: Lemon

    @property
    def urgent(self) -> bool:
        return self.lemon.status == "alert"

    def clear(self) -> dict:
        """What has the service worker close this lemon's notification instead of showing one."""
        return {"clear": self.lemon.channel}

    def message(self, said: str) -> dict:
        """What the service worker shows (`sw.js`), with *said*, the lemon's news, as its text."""
        name = f"{self.lemon.emoji} {self.lemon.name}".strip() or self.lemon.channel
        return {
            "title": name,
            "body": said,
            "tag": self.lemon.channel,
            "url": f"lemon?channel={urllib.parse.quote(self.lemon.channel, safe='')}",
        }


def said(entries: abc.Iterable[abc.Mapping[str, str]], limit: int = 180) -> str:
    """The start of the lemon's last reply in *entries*, its conversation oldest first, on one line."""
    replies = [
        e["text"]
        for e in entries
        if e.get("role") == conversation.entry.LEMON and e.get("text", "").strip()
    ]
    if not replies:
        return ""

    flat = " ".join(replies[-1].split())
    return flat if len(flat) <= limit else flat[: limit - 3].rstrip() + "..."


def _news(before: Lemon | None, after: Lemon) -> bool:
    return after.unread and (before is None or not before.unread or after.updated > before.updated)


def between(before: abc.Mapping[str, Lemon], after: abc.Mapping[str, Lemon]) -> list[Event]:
    return [Event(lemon) for channel, lemon in after.items() if _news(before.get(channel), lemon)]


def read_between(before: abc.Mapping[str, Lemon], after: abc.Mapping[str, Lemon]) -> list[Event]:
    """The lemons that were unread and now are read."""
    return [
        Event(lemon)
        for channel, lemon in after.items()
        if not lemon.unread and channel in before and before[channel].unread
    ]
