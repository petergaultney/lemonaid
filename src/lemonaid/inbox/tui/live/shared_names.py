"""The brief names more than one active lemon holds, for marking them in the inbox.

Looking them up stats every brief, so an inbox refresh reuses the last answer for a minute.
"""

import math
import sqlite3

from .... import brief

_SECONDS = 60.0


class Cache:
    """Mutated only on the UI thread."""

    def __init__(self) -> None:
        self._at = -math.inf
        self._names: frozenset[str] = frozenset()

    def names(self, conn: sqlite3.Connection, idle_days: int, now: float) -> frozenset[str]:
        """Shared names, lowercased."""
        if now - self._at >= _SECONDS:
            since = brief.active_names.window_start(idle_days, now)
            self._at = now
            self._names = frozenset(
                brief.active_names.shared(brief.active_names.holders(conn, since))
            )
        return self._names
