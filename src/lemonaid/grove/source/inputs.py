"""What the grove reads from the inbox, gathered once per refresh.

`from_frame` reuses what the inbox just read; `read` gathers it fresh, for the CLI.
"""

import dataclasses
import sqlite3
import time
from collections import abc

from ... import brief, groups
from ...config import Config
from ...inbox import db, emoji, parent_order, pins, presence, view
from ...inbox.tui.live import inbox_frame
from ...inbox.tui.rows import brief_cards, pr_numbers


@dataclasses.dataclass(frozen=True)
class Inputs:
    rows: list[db.Notification]  # every live lemon, hidden and folded ones included
    cards: dict[str, brief_cards.CardBrief]  # by channel, for lemons with a brief
    memberships: dict[str, tuple[str, ...]]  # each channel's groups, in group order
    groups: list[groups.store.Group]  # in the inbox's order, with their drawn colors
    pinned: frozenset[str]
    emojis: dict[str, str]
    lemon_ids: dict[str, str]
    parents: dict[str, str]  # child channel to parent channel
    births: dict[str, float]  # when lemonaid first heard from each channel
    hidden: frozenset[str]  # channels whose brief says `Hidden: yes`
    numbers: dict[str, tuple[pr_numbers.PR, ...]]  # each channel's PRs, as the inbox shows them


def _births(conn: sqlite3.Connection, channels: abc.Iterable[str]) -> dict[str, float]:
    wanted = list(channels)
    if not wanted:
        return {}

    marks = ",".join("?" * len(wanted))
    return {
        row["channel"]: row["born"]
        for row in conn.execute(
            f"SELECT channel, MIN(created_at) AS born FROM notifications"
            f" WHERE channel IN ({marks}) GROUP BY channel",
            wanted,
        )
    }


def from_frame(conn: sqlite3.Connection, frame: inbox_frame.Frame) -> Inputs:
    active = frame.active
    return Inputs(
        rows=list(active.rows),
        cards=dict(active.cards),
        memberships=dict(active.memberships),
        groups=list(frame.groups),
        pinned=frame.pinned,
        emojis=dict(frame.emojis),
        lemon_ids=brief.identity.by_channel(conn),
        parents=dict(frame.parents),
        births=_births(conn, (n.channel for n in active.rows)),
        hidden=active.hidden_briefs,
        numbers=dict(frame.numbers),
    )


def read(conn: sqlite3.Connection, config: Config, switch_source: str | None) -> Inputs:
    """Lemons switchable from *switch_source* (a terminal kind such as `tmux`), or from any
    terminal when None; headless sessions are left out either way, as the inbox leaves them out.
    """
    now = time.time()
    active = view.ordered_active(
        conn,
        switch_source,
        brief_cards.BriefCache(),
        presence.Probe(),
        config.tui.mid_turn_working,
        now,
    )
    active = dataclasses.replace(
        active, rows=[n for n in active.rows if n.switch_source is not None]
    )
    group_list = groups.store.all_groups(conn)
    colors = groups.color.drawn(group_list, config.tui.group_colors)
    return Inputs(
        rows=list(active.rows),
        cards=dict(active.cards),
        memberships=dict(active.memberships),
        groups=[dataclasses.replace(g, color=colors[g.name]) for g in group_list],
        pinned=frozenset(pins.pinned_positions(conn)),
        emojis=emoji.by_channel(conn),
        lemon_ids=brief.identity.by_channel(conn),
        parents=parent_order.channels(conn),
        births=_births(conn, (n.channel for n in active.rows)),
        hidden=active.hidden_briefs,
        # From briefs alone: a branch's PR comes from a place's `open_prs` command, which the
        # inbox runs on its own schedule.
        numbers=pr_numbers.rows(conn, active.rows, config.places, pr_numbers.Cache()),
    )
