"""GitHub snapshots of PRs, kept for a few minutes so inbox refreshes stay cheap and offline-safe."""

from collections import abc

from ..watch import pr_activity
from . import pulls

_TTL_SECONDS = 300.0


class Cache:
    """Mutated only on the UI thread; workers fetch and hand the snapshot to `store`."""

    def __init__(self) -> None:
        self._found: dict[pulls.Key, tuple[float, pr_activity.Snapshot | None]] = {}
        self._pending: set[pulls.Key] = set()

    def due(self, keys: abc.Iterable[pulls.Key], now: float) -> list[pulls.Key]:
        """The keys to fetch now; each is handed out once until it is stored."""
        due = [
            key
            for key in dict.fromkeys(keys)
            if key not in self._pending
            and (key not in self._found or now - self._found[key][0] >= _TTL_SECONDS)
        ]
        self._pending.update(due)
        return due

    def store(self, key: pulls.Key, snap: pr_activity.Snapshot | None, now: float) -> None:
        """A failed fetch keeps the last good snapshot, and waits out the TTL before retrying."""
        previous = self._found.get(key)
        self._found[key] = (now, snap or (previous[1] if previous else None))
        self._pending.discard(key)

    def snapshots(self) -> dict[pulls.Key, pr_activity.Snapshot | None]:
        return {key: snap for key, (_at, snap) in self._found.items()}
