"""What one inbox refresh reads from the database, before it arranges and draws."""

import dataclasses
import sqlite3
from collections import abc

from .... import brief, groups, palette
from ....config import Config
from ... import db, emoji, order, pins, presence, search, view
from ..rows import brief_cards, pr_numbers
from ..watchers import focus


@dataclasses.dataclass(frozen=True)
class Frame:
    active: view.Active
    pinned: frozenset[str]
    focused_channels: frozenset[str]
    shown: list[db.Notification]
    folded: list[db.Notification]
    emojis: dict[str, str]
    groups: list[groups.store.Group]
    wordybins: dict[str, str]
    other: list[db.Notification]  # live sessions switchable only from another terminal
    numbers: dict[str, pr_numbers.PR]
    matching_ids: set[int] | None  # None outside a search


def ordered_active(
    conn: sqlite3.Connection,
    switch_source: str | None,
    config: Config,
    brief_cache: brief_cards.BriefCache,
    probe: presence.Probe,
    now: float,
) -> view.Active:
    return view.ordered_active(
        conn, switch_source, brief_cache, probe, config.tui.mid_turn_working, now
    )


def load(
    conn: sqlite3.Connection,
    config: Config,
    brief_cache: brief_cards.BriefCache,
    probe: presence.Probe,
    pr_cache: pr_numbers.Cache,
    *,
    env_filter: str | None,
    focused: frozenset[str],
    search_text: str | None,
    current_key: str | None,
    other_key: str | None,
    unfolded_ids: abc.Set[str],
    now: float,
) -> Frame:
    """`env_filter` names the terminal this inbox switches in, if known; `search_text` is
    None outside a search. `current_key` and `other_key` are the cursor's rows.
    """
    pinned = frozenset(pins.pinned_positions(conn))
    # Main table: only sessions switchable from the current environment
    active = ordered_active(conn, env_filter, config, brief_cache, probe, now)
    focused_channels = focus.channels(active.rows, focused)
    matching_ids = (
        {result.notification.id for result in search.find(conn, search_text)}
        | {n.id for n in active.rows if n.channel in active.deaf}
        if search_text is not None
        else None
    )
    in_view = {
        n.channel for n in active.rows if n.channel in focused_channels or str(n.id) == current_key
    }
    shown, folded = order.fold(
        view.inbox_rows(active, pinned, in_view),
        view.statuses(active.cards, active.rows),
        pinned,
        config.tui.fold_statuses,
        {
            n.channel
            for n in active.rows
            if n.channel in focused_channels
            or (str(n.id) == current_key and current_key in unfolded_ids)
        },
        active.deaf,
    )  # a focused lemon stays out of the fold, and so does the cursor's row until the cursor leaves it
    group_list = groups.store.all_groups(conn)
    colours = palette.assign_groups((g.name for g in group_list), config.tui.group_colors)
    # Lower pane: live sessions from other switchable terminals.
    # Headless sessions (switch_source IS NULL) are excluded — they can't be
    # switched to from anywhere, so they belong in history instead.
    if env_filter:
        other_active = ordered_active(conn, None, config, brief_cache, probe, now)
        if matching_ids is not None:
            matching_ids |= {n.id for n in other_active.rows if n.channel in other_active.deaf}
        other_in_view = {
            n.channel
            for n in other_active.rows
            if n.metadata.get("tty", "") in focused or str(n.id) in {current_key, other_key}
        }
        other = [
            n
            for n in view.inbox_rows(other_active, pinned, other_in_view)
            if n.switch_source is not None and n.switch_source != env_filter
        ]
    else:
        other = []

    return Frame(
        active,
        pinned,
        focused_channels,
        shown,
        folded,
        emoji.by_channel(conn),
        [dataclasses.replace(g, colour=colours[g.name]) for g in group_list],
        {c: brief.identity.brief_name(i) for c, i in brief.identity.by_channel(conn).items()}
        if config.tui.brief_names_in_inbox
        else {},
        other,
        pr_numbers.rows(conn, [*active.rows, *other], config.places, pr_cache),
        matching_ids,
    )
