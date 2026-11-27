"""Telling each device that turned push notifications on which lemons have news since the server
last read the grove, at most once a minute per lemon, and which of those have since been read."""

import base64
import hashlib
import threading
import time
import urllib.parse
from collections import abc

from ....inbox import db
from ....log import get_logger
from ...model import Lemon
from ...tui.frame import Grove
from .. import lemon
from . import devices, events, webpush

_log = get_logger("grove.web.push")

_NO_CLEARS = {"web.push.apple.com"}
QUIET_SECONDS = 60.0  # a lemon's events closer together than this after its last are dropped


def _lemons(grove: Grove) -> dict[str, Lemon]:
    return {
        each.channel: each for block in grove.blocks for tree in block.trees for each in tree.lemons
    }


def _topic(channel: str) -> str:
    """A Web Push Topic: at most 32 base64url characters."""
    return (
        base64.urlsafe_b64encode(hashlib.blake2b(channel.encode(), digest_size=16).digest())
        .rstrip(b"=")
        .decode()
    )


def _said(channel: str) -> str:
    """The start of the lemon's last reply, else the first line of its inbox message."""
    replied = events.said(lemon.talk(channel).get("entries", []))
    if replied:
        return replied

    with db.connect() as conn:
        row = db.get_by_channel(conn, channel, unread_only=False)
    return (row.message if row else "").strip().split("\n")[0][:180]


def _push(
    message: dict, to: abc.Iterable[webpush.Subscription], urgent: bool, topic: str
) -> list[str]:
    """Send *message* to each device, returning the endpoints that took it."""
    pem, took = devices.key(), []
    for device in to:
        try:
            webpush.send(device, message, pem, urgent=urgent, topic=topic)
            took.append(device.endpoint)
        except webpush.Gone:
            _log.info("a device dropped its push subscription; forgetting it")
            devices.remove(device.endpoint)
        except (OSError, ValueError):  # ValueError: keys stored before `webpush.check`
            _log.exception("couldn't push to a device")
    return took


def _deliver(event: events.Event, to: abc.Iterable[webpush.Subscription]) -> list[str]:
    channel = event.lemon.channel
    return _push(event.message(_said(channel)), to, event.urgent, _topic(channel))


def _clear(event: events.Event, to: abc.Iterable[webpush.Subscription]) -> None:
    """Same topic as the news, so a clear replaces news a phone hasn't fetched yet."""
    _push(event.clear(), to, False, _topic(event.lemon.channel))


def _clearable(endpoints: abc.Iterable[str]) -> list[str]:
    """Safari revokes a subscription whose push shows no notification, which a clear doesn't.
    Chrome and Firefox allow it now and then."""
    return [e for e in endpoints if urllib.parse.urlsplit(e).hostname not in _NO_CLEARS]


class Pusher:
    def __init__(self) -> None:
        self._last: dict[str, Lemon] | None = None
        self._sent: dict[str, float] = {}
        self._told: dict[str, set[str]] = {}  # each lemon's devices showing its news, by endpoint
        self._lock = threading.Lock()  # the server reloads from more than one thread

    def saw(self, grove: Grove) -> None:
        """Send what changed since the last read, in the background. The first read only looks."""
        now, at, due, cleared = _lemons(grove), time.monotonic(), [], []
        with self._lock:
            last, self._last = self._last, now
            if last is None or not webpush.available():
                return

            for event in events.between(last, now):
                if at - self._sent.get(event.lemon.channel, -QUIET_SECONDS) < QUIET_SECONDS:
                    continue
                self._sent[event.lemon.channel] = at
                due.append(event)
            for event in events.read_between(last, now):
                told = self._told.pop(event.lemon.channel, set())
                if told:
                    cleared.append((event, told))
        if due or cleared:
            threading.Thread(target=self._send, args=(due, cleared), daemon=True).start()

    def _record(self, channel: str, took: list[str]) -> list[str]:
        """Records the devices shown *channel*'s news, and returns those to clear now: all of them
        when it was read while they were sent to, as that read went by with nothing to clear."""
        with self._lock:
            now = self._last.get(channel) if self._last else None
            if now is not None and not now.unread:
                return _clearable(took)

            self._told.setdefault(channel, set()).update(_clearable(took))
            return []

    def _send(self, due: list[events.Event], cleared: list[tuple[events.Event, set[str]]]) -> None:
        try:
            to = devices.all_devices()
            for event in due:
                late = self._record(event.lemon.channel, _deliver(event, to))
                if late:
                    _clear(event, [device for device in to if device.endpoint in late])
            for event, told in cleared:
                _clear(event, [device for device in to if device.endpoint in told])
        except Exception:  # a sending thread's top
            _log.exception("couldn't send push notifications")
