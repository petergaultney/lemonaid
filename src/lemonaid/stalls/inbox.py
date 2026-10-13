"""The stuck line of each inbox card, recomputed every half minute from cached GitHub facts."""

import dataclasses
import sqlite3
from .. import brief
from ..config import Config
from ..inbox import view
from ..watch import pr_activity
from . import cache, pulls, report

_RECOMPUTE_SECONDS = 30.0


def lemons(conn: sqlite3.Connection, active: view.Active) -> list[pulls.Lemon]:
    names = brief.identity.by_channel(conn)
    return [
        pulls.Lemon(
            channel,
            path,
            brief.identity.brief_name(names.get(channel, "")),
            card.status,
            card.mid_turn,
            card.since,
            channel in active.reviewers,
        )
        for channel, path in active.briefs.items()
        if (card := active.cards.get(channel))
    ]


class Tracker:
    """Mutated only on the UI thread. `fetch` is what a worker runs for each key `due` names."""

    def __init__(self) -> None:
        self._cache = cache.Cache()
        self._pulls: list[pulls.Pull] = []
        self._at = float("-inf")

    def mark(
        self,
        conn: sqlite3.Connection,
        active: view.Active,
        config: Config,
        now: float,
    ) -> view.Active:
        """*active* with each stuck lemon's card carrying its stuck line."""
        if now - self._at >= _RECOMPUTE_SECONDS:
            self._at = now
            self._pulls = pulls.find(lemons(conn, active), config.brief.vaults)

        found = report.find(self._pulls, self._cache.snapshots(), now, config.inbox.stall_minutes)
        stuck = {stall.channel: stall.line for stall in reversed(found)}
        return dataclasses.replace(
            active,
            cards={
                channel: dataclasses.replace(card, stuck=stuck.get(channel, ""))
                for channel, card in active.cards.items()
            },
        )

    def due(self, now: float) -> list[pulls.Key]:
        return self._cache.due((pull.key for pull in self._pulls), now)

    def store(self, key: pulls.Key, snap: pr_activity.Snapshot | None, now: float) -> None:
        self._cache.store(key, snap, now)
        self._at = float("-inf")  # so the next refresh sees it


def fetch(key: pulls.Key) -> pr_activity.Snapshot | None:
    return pr_activity.fetch(key[0], int(key[1]), ())
