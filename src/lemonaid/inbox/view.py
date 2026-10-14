"""The rows the inbox draws, in its own order, and the snapshot of them an arranger is sent.

The TUI and `lemonaid inbox arrange` both build the inbox's rows here, so an
arranger tested from the CLI sees what `lma` would send it.
"""

import dataclasses
import re
import sqlite3
from collections import abc
from pathlib import Path
from typing import Any

from .. import brief
from ..lineage import links as lineage_links
from . import author_sibling, db, order, pins, presence, status_since, turns
from .tui.rows import brief_cards

SNAPSHOT_VERSION = 1


@dataclasses.dataclass(frozen=True)
class Active:
    rows: list[db.Notification]  # in the inbox's own order
    cards: dict[str, brief_cards.CardBrief]  # by channel
    briefs: dict[str, Path]  # the attached brief's path, by channel
    reviewers: frozenset[str]  # channels whose stable brief ID starts with review-
    memberships: dict[str, tuple[str, ...]] = dataclasses.field(
        default_factory=dict
    )  # each channel's group names, in group order

    @property
    def deaf(self) -> frozenset[str]:
        """Channels of lemons marked `deaf`: never folded, filtered or collapsed away."""
        return frozenset(
            channel for channel, card in self.cards.items() if card.mark == presence.DEAF
        )


def _cards(
    conn: sqlite3.Connection,
    rows: abc.Sequence[db.Notification],
    attached: abc.Mapping[str, Path],
    cache: brief_cards.BriefCache,
    probe: presence.Probe,
    mid_turn_working: bool,
    now: float,
) -> dict[str, brief_cards.CardBrief]:
    """The card of each attached brief by channel, with its lemon's turn and presence."""
    working = turns.briefs(rows, attached, now)
    asking = {n.channel for n in rows if n.asks}
    found = {
        channel: (path, card) for channel, path in attached.items() if (card := cache.get(path))
    }
    lemon_ids = brief.identity.by_channel(conn)
    marks = probe.marks(
        rows,
        {
            channel: lemon_ids[channel]
            for channel, (_path, card) in found.items()
            if channel in lemon_ids and card.status != "done"
        },
        now,
    )
    cards = {
        channel: dataclasses.replace(
            card,
            mid_turn=path in working,
            held_mid_turn=mid_turn_working,
            mark=marks.get(channel, ""),
            asking=channel in asking,
        )
        for channel, (path, card) in found.items()
    }
    since = status_since.observe(
        conn, {found[channel][0]: (card.status, card.mtime) for channel, card in cards.items()}
    )
    # Without a status, an idle lemon's time counts from its last report, which ends a turn;
    # an edit to its brief by anyone else says nothing about it.
    reported = {n.channel: n.created_at for n in rows}
    return {
        channel: dataclasses.replace(
            card,
            since=since[found[channel][0]] if card.status else reported.get(channel, card.mtime),
        )
        for channel, card in cards.items()
    }


def _memberships(conn: sqlite3.Connection) -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    for row in conn.execute(
        "SELECT b.channel, g.name FROM session_briefs b"
        " JOIN lemon_identities i ON i.path = b.path"
        " JOIN lemon_group_members m ON m.lemon_id = i.lemon_id"
        " JOIN lemon_groups g ON g.group_id = m.group_id"
        " ORDER BY g.position, g.group_id"
    ):
        found[row["channel"]] = (*found.get(row["channel"], ()), row["name"])
    return found


def statuses(
    cards: abc.Mapping[str, brief_cards.CardBrief], rows: abc.Iterable[db.Notification]
) -> dict[str, str]:
    """The status that places each lemon in the list and the fold, by channel.

    A lemon stuck on a permission prompt is `blocked`, with or without a brief.
    """
    return {
        **{n.channel: "blocked" for n in rows if n.asks},
        **{channel: card.placed for channel, card in cards.items()},
    }


def inbox_rows(
    active: Active, pinned: abc.Container[str], in_view: abc.Container[str]
) -> list[db.Notification]:
    """Omit quiet reviewers unless the user chose them, they are deaf, or their status needs a band."""
    brief_statuses = statuses(active.cards, active.rows)
    return [
        row
        for row in active.rows
        if row.channel not in active.reviewers
        or row.channel in pinned
        or row.channel in in_view
        or row.channel in active.deaf
        or order.special_status(brief_statuses.get(row.channel, ""))
    ]


def _parent_id(text: str) -> str:
    """The stable Lemon-ID in a generated `Parent:` line, if present."""
    for line in text.splitlines():
        if not line.startswith("Parent:"):
            continue
        for match in re.finditer(r"(?<![\w.-])([\w-]+\.[A-Za-z]+)(?![\w.-])", line):
            if brief.identity.valid(match.group(1)):
                return match.group(1)
    return ""


def _has_author_parent(conn: sqlite3.Connection, brief_id: str, path: Path) -> bool:
    """Hide reviewers whose brief names a worker as parent, not a coordinator."""
    text = path.read_text()
    parent_id = _parent_id(text) or lineage_links.parent_of(conn, brief_id)
    if not parent_id:
        return False

    if re.search(
        r"\b(?:control[ -]center|hq|peter|lemonaid-plan-manager)\b",
        parent_id,
        re.IGNORECASE,
    ):
        return author_sibling.has_author_sibling(conn, brief_id, text, parent_id)

    # A lead has workers of its own. The brief's Parent line takes precedence
    # over lineage because `--parent parent` links the reviewer under the
    # author's parent while the generated line still names the author. That
    # author-started reviewer stays quiet; a lead-parented brief with no
    # author sibling on its PR remains visible.
    return not any(
        not brief.identity.brief_description(child_id).startswith("review-")
        for child_id in lineage_links.children_of(conn, parent_id)
        if child_id != brief_id
    ) or author_sibling.has_author_sibling(conn, brief_id, text, parent_id)


def ordered_active(
    conn: sqlite3.Connection,
    switch_source: str | None,
    cache: brief_cards.BriefCache,
    probe: presence.Probe,
    mid_turn_working: bool,
    now: float,
) -> Active:
    """Active sessions in the order they are drawn, with their briefs.

    Both layouts go through here, so the sidebar and the wide inbox list
    sessions in the same order whether or not either shows brief status.
    """
    rows = db.get_active(conn, switch_source=switch_source)
    attached = brief.attached.for_rows(conn, rows)
    cards = _cards(conn, rows, attached, cache, probe, mid_turn_working, now)
    brief_ids = brief.identity.by_channel(conn)
    reviewers = frozenset(
        channel
        for channel, brief_id in brief_ids.items()
        if channel in attached
        and brief.identity.brief_description(brief_id).startswith("review-")
        and _has_author_parent(conn, brief_id, attached[channel])
    )
    return Active(
        order.by_status(rows, statuses(cards, rows), pins.pinned_positions(conn)),
        cards,
        attached,
        reviewers,
        _memberships(conn),
    )


def _brief(card: brief_cards.CardBrief | None, path: Path | None) -> dict[str, Any] | None:
    if card is None or path is None:
        return None

    return {
        "path": str(path),
        "status": card.status,
        "shown": card.shown,
        "mark": card.mark,
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
    placed = card.placed if card else "blocked" if n.asks else ""
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
        "groups": list(active.memberships.get(n.channel, ())),
        "default": {
            "position": position,
            "band": order.band(placed, n.is_unread, n.channel in pinned),
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
