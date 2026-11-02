"""Facts about lemons for a checker: each one's state, and the lineage above it.

A lemon is live while its brief is attached, not archived, and its harness runs.
"""

import sqlite3
import typing as ty

from ...lemon_facts import facts
from ...lineage import links
from ...messages import recipient
from ..model import identities
from . import live


def lemon(lemon_id: str, seen: facts.Facts | None, now: float) -> list[live.Fact]:
    """`attached`, `available`, `live`, `activity` and `idle_since` for one lemon; a brief
    with no running lemon is unattached, and one with no attachment at all is unavailable."""
    if seen is None:
        return [
            live.fact("lemon", lemon_id, "attached", "false", now),
            live.fact("lemon", lemon_id, "available", "true", now),
            live.fact("lemon", lemon_id, "live", "false", now),
        ]

    gone = seen.archived or seen.state == recipient.DEAD
    alive = seen.harness_running
    return [
        live.fact(
            "lemon",
            lemon_id,
            "attached",
            str(bool(alive)).lower(),
            now,
            "known" if alive is not None else "unknown",
        ),
        live.fact("lemon", lemon_id, "available", str(not gone).lower(), now),
        live.fact(
            "lemon",
            lemon_id,
            "live",
            str(bool(alive) and not gone).lower(),
            now,
            "known" if alive is not None or gone else "unknown",
        ),
        live.fact(
            "lemon",
            lemon_id,
            "activity",
            "active" if seen.state == recipient.MID_TURN else "idle",
            now,
        ),
        live.fact(
            "lemon",
            lemon_id,
            "idle_since",
            live.stamp(seen.last_activity) if seen.last_activity else "",
            now,
            "known" if seen.last_activity else "unknown",
        ),
    ]


def lineage(
    conn: sqlite3.Connection, lemon_id: str, seen: ty.Mapping[str, facts.Facts], now: float
) -> list[live.Fact]:
    """`chain`, *lemon_id* and its ancestors nearest first, and each one's `live` fact."""
    chain: list[str] = []
    who = identities.current(conn, lemon_id) or lemon_id
    while who and who not in chain:
        chain.append(who)
        who = links.parent_of(conn, who)
    return [
        live.fact("lineage", lemon_id, "chain", " ".join(chain), now),
        *(f for who in chain for f in lemon(who, seen.get(who), now) if f["field"] == "live"),
    ]
