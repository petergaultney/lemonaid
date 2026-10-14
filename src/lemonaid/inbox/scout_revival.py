"""Restart the push scout of each Claude lemon the inbox marks `deaf`.

A scout that dies while its lemon is idle leaves nothing running in that lemon to notice,
so the live inbox, which already marks it deaf, starts a new one. Attempts per lemon are
spaced out, since a session that would hold pushed messages never gets a scout.
"""

from collections import abc
from pathlib import Path

from .. import brief
from ..log import get_logger
from ..watch import push_scout

_log = get_logger("inbox.scout_revival")

RETRY_SECONDS = 60.0


class Revival:
    def __init__(self) -> None:
        self._tried: dict[str, float] = {}

    def due(self, deaf: abc.Iterable[str], now: float) -> list[str]:
        """The deaf Claude channels to try now; each is tried at most once per `RETRY_SECONDS`."""
        due = [
            channel
            for channel in deaf
            if channel.startswith("claude:")
            and now - self._tried.get(channel, float("-inf")) >= RETRY_SECONDS
        ]
        self._tried.update((channel, now) for channel in due)
        return due


def revive(channel: str, brief_path: Path) -> bool:
    """Whether the lemon in *channel* has a watcher once this returns."""
    try:
        lemon_id = brief.identity.from_path(brief_path)
    except (OSError, ValueError) as error:
        _log.info("no scout for %s: %s", channel, error)
        return False

    started = push_scout.ensure(channel.removeprefix("claude:"), lemon_id)
    if started:
        _log.info("restarted the push scout for deaf %s (%s)", lemon_id, channel)
    return started
