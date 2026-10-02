"""The rows the inbox draws, in its own order, and the snapshot of them an arranger is sent.

The TUI and `lemonaid inbox arrange` both build the inbox's rows here, so an
arranger tested from the CLI sees what `lma` would send it.
"""

import dataclasses
import sqlite3
from collections import abc
from pathlib import Path
from typing import Any

from .. import brief
from . import db, order, pins, status_since, turns
from .tui import brief_cards

SNAPSHOT_VERSION = 1


@dataclasses.dataclass(frozen=True)
class Active:
    rows: list[db.Notification]  # in the inbox's own order
    cards: dict[str, brief_cards.CardBrief]  # by channel
    briefs: dict[str, Path]  # the attached brief's path, by channel


def _cards(
    conn: sqlite3.Connection,
    rows: abc.Iterable[db.Notification],
    attached: abc.Mapping[str, Path],
    cache: brief_cards.BriefCache,
    mid_turn_working: bool,
    now: float,
) -> dict[str, brief_cards.CardBrief]:
    """The card of each attached brief by channel, marked while its lemon is mid-turn."""
    working = turns.briefs(rows, attached, now) if mid_turn_working else frozenset()
    found = {
        channel: (path, card) for channel, path in attached.items() if (card := cache.get(path))
    }
    since = status_since.observe(
        conn, {path: (card.status, card.mtime) for path, card in found.values()}
    )
    return {
        channel: dataclasses.replace(
            brief_cards.mid_turn(card) if path in working else card, since=since[path]
        )
        for channel, (path, card) in found.items()
    }


def statuses(cards: abc.Mapping[str, brief_cards.CardBrief]) -> dict[str, str]:
    return {channel: card.status for channel, card in cards.items()}


def ordered_active(
    conn: sqlite3.Connection,
    switch_source: str | None,
    cache: brief_cards.BriefCache,
    mid_turn_working: bool,
    now: float,
) -> Active:
    """Active sessions in the order they are drawn, with their briefs.

    Both layouts go through here, so the sidebar and the wide inbox list
    sessions in the same order whether or not either shows brief status.
    """
    rows = db.get_active(conn, switch_source=switch_source)
    attached = brief.attached.for_rows(conn, rows)
    cards = _cards(conn, rows, attached, cache, mid_turn_working, now)
    return Active(
        order.by_status(rows, statuses(cards), pins.pinned_positions(conn)), cards, attached
    )


def _brief(card: brief_cards.CardBrief | None, path: Path | None) -> dict[str, Any] | None:
    if card is None or path is None:
        return None

    return {
        "path": str(path),
        "status": card.status,
        "shown": card.shown,
        "needs_label": card.needs_label,
        "needs": card.needs,
        "waiting_on": card.waiting_on,
        "running": card.running,
        "mtime": card.mtime,
        "since": card.since,
    }


def _row(
    n: db.Notification,
    active: Active,
    pinned: abc.Container[str],
    emojis: abc.Mapping[str, str],
    position: int,
    folded: bool,
    now: float,
) -> dict[str, Any]:
    card = active.cards.get(n.channel)
    return {
        "id": n.id,
        "channel": n.channel,
        "backend": n.channel.split(":", 1)[0],
        "name": n.name or "",
        "emoji": emojis.get(n.channel, ""),
        "unread": n.is_unread,
        "pinned": n.channel in pinned,
        "mid_turn": turns.mid_turn(n, now),
        "message": n.message,
        "created_at": n.created_at,
        "read_at": n.read_at,
        "cwd": n.metadata.get("cwd", ""),
        "branch": n.metadata.get("git_branch", ""),
        "tty": n.metadata.get("tty", ""),
        "brief": _brief(card, active.briefs.get(n.channel)),
        "default": {
            "position": position,
            "band": order.band(card.status if card else "", n.is_unread, n.channel in pinned),
            "folded": folded,
        },
    }


def snapshot(
    active: Active,
    shown: abc.Sequence[db.Notification],
    folded: abc.Sequence[db.Notification],
    pinned: abc.Container[str],
    emojis: abc.Mapping[str, str],
    layout: str,
    width: int,
    now: float,
) -> dict[str, Any]:
    """What an arranger is sent, less `now`: *shown* then *folded* are the inbox's own answer.

    `now` is left out so that two snapshots compare equal while nothing has
    changed; the arranger's caller adds it when it sends one.
    """
    return {
        "version": SNAPSHOT_VERSION,
        "layout": layout,
        "width": width,
        "rows": [
            _row(n, active, pinned, emojis, position, position >= len(shown), now)
            for position, n in enumerate([*shown, *folded])
        ],
    }
