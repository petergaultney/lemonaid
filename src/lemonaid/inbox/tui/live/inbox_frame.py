"""What one inbox refresh reads from the database, before it arranges and draws."""

import dataclasses
import sqlite3
from collections import abc

from .... import brief, groups
from ....config import Config
from ....stalls import inbox as stalls_inbox
from ... import db, emoji, pins, presence, search, view
from ..rows import brief_cards, pr_numbers
from ..watchers import focus


@dataclasses.dataclass(frozen=True)
class Frame:
    active: "view.Active"
    pinned: frozenset[str]
    focused_channels: frozenset[str]
    shown: list[db.Notification]
    folded: list[db.Notification]
    hidden: frozenset[str]  # channels folded for being hidden
    emojis: dict[str, str]
    groups: list[groups.store.Group]
    wordybins: dict[str, str]
    other: list[db.Notification]  # live sessions switchable only from another terminal
    numbers: dict[str, tuple[pr_numbers.PR, ...]]
    matching_ids: set[int] | None  # None outside a search


def _brief_names(conn: sqlite3.Connection, shared: abc.Set[str]) -> dict[str, str]:
    """Each session's brief name, marked when another active lemon holds it too."""
    names = {c: brief.identity.brief_name(i) for c, i in brief.identity.by_channel(conn).items()}
    return {c: f"{n} (shared)" if n.lower() in shared else n for c, n in names.items()}


def ordered_active(
    conn: sqlite3.Connection,
    switch_source: str | None,
    config: Config,
    brief_cache: brief_cards.BriefCache,
    probe: presence.Probe,
    stalls: stalls_inbox.Tracker,
    now: float,
) -> "view.Active":
    return stalls.mark(
        conn,
        view.ordered_active(
            conn, switch_source, brief_cache, probe, config.tui.mid_turn_working, now
        ),
        config,
        now,
    )


def _switchable_from(active: "view.Active", source: str) -> "view.Active":
    """*active* cut down to the sessions switchable from *source*, in the same order."""
    rows = [n for n in active.rows if n.switch_source == source]
    channels = {n.channel for n in rows}
    return dataclasses.replace(
        active,
        rows=rows,
        cards={c: card for c, card in active.cards.items() if c in channels},
        briefs={c: path for c, path in active.briefs.items() if c in channels},
        reviewers=active.reviewers & channels,
    )


def load(
    conn: sqlite3.Connection,
    config: Config,
    brief_cache: brief_cards.BriefCache,
    probe: presence.Probe,
    pr_cache: pr_numbers.Cache,
    stalls: stalls_inbox.Tracker,
    *,
    env_filter: str | None,
    focused: frozenset[str],
    search_text: str | None,
    current_key: str | None,
    other_key: str | None,
    unfolded_ids: abc.Set[str],
    shared_names: abc.Set[str],
    now: float,
) -> Frame:
    """`env_filter` names the terminal this inbox switches in, if known; `search_text` is
    None outside a search. `current_key` and `other_key` are the cursor's rows.
    """
    pinned = frozenset(pins.pinned_positions(conn))
    # Every live session is read once; the main table is those switchable from here.
    everything = ordered_active(conn, None, config, brief_cache, probe, stalls, now)
    active = _switchable_from(everything, env_filter) if env_filter else everything
    focused_channels = focus.channels(active.rows, focused)
    matching_ids = (
        {result.notification.id for result in search.find(conn, search_text)}
        | {n.id for n in active.rows if n.channel in active.deaf}
        if search_text is not None
        else None
    )
    in_view = {
        n.channel
        for n in active.rows
        if n.channel in focused_channels
        or str(n.id) == current_key
        or (matching_ids is not None and n.id in matching_ids)
    }
    shown, folded, hidden = view.default_fold(
        active,
        pinned,
        in_view,
        config.tui.fold_statuses,
        bool(config.inbox.arrange),
        {
            n.channel
            for n in active.rows
            if n.channel in focused_channels
            or (str(n.id) == current_key and current_key in unfolded_ids)
        },
    )  # a focused lemon stays out of the fold, and so does the cursor's row until the cursor leaves it
    identities = brief.identity.by_channel(conn)
    current_members = {identities[n.channel] for n in active.rows if n.channel in identities}
    group_list = [
        dataclasses.replace(g, members=tuple(m for m in g.members if m in current_members))
        for g in groups.store.all_groups(conn)
    ]
    colors = groups.color.drawn(group_list, config.tui.group_colors)
    # Lower pane: live sessions from other switchable terminals.
    # Headless sessions (switch_source IS NULL) are excluded — they can't be
    # switched to from anywhere, so they belong in history instead.
    if env_filter:
        if matching_ids is not None:
            matching_ids |= {n.id for n in everything.rows if n.channel in everything.deaf}
        other_in_view = {
            n.channel
            for n in everything.rows
            if n.metadata.get("tty", "") in focused
            or str(n.id) in {current_key, other_key}
            or (matching_ids is not None and n.id in matching_ids)
        }
        other = [
            n
            for n in view.inbox_rows(everything, pinned, other_in_view)
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
        hidden,
        emoji.by_channel(conn),
        [dataclasses.replace(g, color=colors[g.name]) for g in group_list],
        _brief_names(conn, shared_names) if config.tui.brief_names_in_inbox else {},
        other,
        pr_numbers.rows(conn, [*active.rows, *other], config.places, pr_cache),
        matching_ids,
    )
