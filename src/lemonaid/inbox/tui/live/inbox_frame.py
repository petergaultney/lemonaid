"""What one inbox refresh reads from the database, before it arranges and draws."""

import dataclasses
import sqlite3
from collections import abc

from .... import brief, groups
from ....config import Config
from ....stalls import inbox as stalls_inbox
from ... import (
    attention,
    db,
    emoji,
    lemon_items,
    parent_order,
    pins,
    presence,
    search,
    sections,
    view,
)
from ..rows import brief_cards, pr_numbers
from ..watchers import focus


@dataclasses.dataclass(frozen=True)
class Request:
    """What one load reads, taken from the UI before it starts; `seq` orders them."""

    seq: int
    focused: frozenset[str]
    env_filter: str | None
    search_text: str | None  # None outside a search
    current_key: str | None
    other_key: str | None
    unfolded_ids: frozenset[str]
    attention: bool = False


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
    parents: dict[str, str] = dataclasses.field(default_factory=dict)
    child_totals: dict[str, int] = dataclasses.field(default_factory=dict)
    # a lemon item's channel to its lemon's, drawn beside that lemon but not as its child
    attached: dict[str, str] = dataclasses.field(default_factory=dict)
    request: int = 0  # the `Request.seq` it was loaded for
    search_text: str | None = None


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


def _without_read_items(active: "view.Active") -> "view.Active":
    """*active* less the lemon items read already that asked to leave once read; history
    still has them."""
    rows = [n for n in active.rows if not lemon_items.hidden_when_read(n)]
    return dataclasses.replace(active, rows=rows)


def _attached(active: "view.Active") -> dict[str, str]:
    """Each lemon item whose lemon is live in some terminal, by channel, to that lemon's
    channel. A lemon with no terminal is in neither pane, so its item shows on its own."""
    live = {n.channel for n in active.rows if n.switch_source is not None}
    return {
        n.channel: lemon
        for n in active.rows
        if (lemon := lemon_items.lemon_of(n)) and lemon in live and lemon != n.channel
    }


def _with_attached(active: "view.Active", attached: abc.Mapping[str, str]) -> "view.Active":
    """*active* with each lemon item in its lemon's groups, so it is drawn there."""
    memberships = dict(active.memberships)
    for row, lemon in attached.items():
        memberships[row] = memberships.get(lemon, ())
    return dataclasses.replace(active, memberships=memberships)


def _switchable_from(
    active: "view.Active", source: str, attached: abc.Mapping[str, str]
) -> "view.Active":
    """*active* cut down to the sessions switchable from *source*, in the same order, and the
    items of those sessions, which belong to no terminal of their own. An unread item whose
    lemon is gone, or that names none, shows in every terminal, on its own."""
    here = {n.channel for n in active.rows if n.switch_source == source}
    rows = [
        n
        for n in active.rows
        if n.channel in here
        or attached.get(n.channel) in here
        or (lemon_items.is_item(n) and n.channel not in attached and n.is_unread)
    ]
    channels = {n.channel for n in rows}
    return dataclasses.replace(
        active,
        rows=rows,
        cards={c: card for c, card in active.cards.items() if c in channels},
        briefs={c: path for c, path in active.briefs.items() if c in channels},
        hidden_briefs=active.hidden_briefs & channels,
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
    attention_mode: bool = False,
) -> Frame:
    """`env_filter` names the terminal this inbox switches in, if known; `search_text` is
    None outside a search. `current_key` and `other_key` are the cursor's rows.
    """
    pinned = frozenset(pins.pinned_positions(conn))
    # Every live session is read once; the main table is those switchable from here.
    everything = _without_read_items(
        ordered_active(conn, None, config, brief_cache, probe, stalls, now)
    )
    attached = _attached(everything)
    everything = _with_attached(everything, attached)
    active = _switchable_from(everything, env_filter, attached) if env_filter else everything
    focused_channels = focus.channels(active.rows, focused)
    matching_ids = (
        {result.notification.id for result in search.find(conn, search_text)}
        | {n.id for n in active.rows if n.channel in focused_channels}
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
        attention.rule(config.tui, attention_mode),
        bool(config.inbox.arrange),
        {
            n.channel
            for n in active.rows
            if n.channel in focused_channels
            or (matching_ids is not None and n.id in matching_ids)
            or (str(n.id) == current_key and current_key in unfolded_ids)
            # an item still to read is what attention mode is for, though it has no status
            or (lemon_items.is_item(n) and n.is_unread)
        },
    )  # a focused lemon, search match or item to read stays out of the fold, and so does the cursor's row until the cursor leaves it
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
        elsewhere = [
            n
            for n in view.inbox_rows(everything, pinned, other_in_view)
            if n.switch_source is not None and n.switch_source != env_filter
        ]
        # every session of another terminal, hidden ones too, which an unread item brings back
        lemons_elsewhere = [
            n
            for n in everything.rows
            if n.switch_source is not None and n.switch_source != env_filter
        ]
        theirs = {n.channel for n in lemons_elsewhere}
        other = sections.beside_their_lemons(
            [
                *elsewhere,
                *(n for n in everything.rows if attached.get(n.channel) in theirs),
            ],
            attached,
            lemons_elsewhere,
        )
    else:
        other = []

    parents = parent_order.channels(conn)
    totals = parent_order.counts((n.channel for n in db.get_active(conn)), parents)
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
        parents,
        totals,
        attached=attached,
    )
