"""The inbox list cut into groups: each under a header line, in manual order.

Pinned rows in no group come first. The remaining rows in no group keep their
incoming order, before or after groups in their stored order.

A group is its header, its pinned and deaf rows, which stay when it's collapsed, and
unless it's collapsed the rest of its rows, bar any the caller keeps drawn. A
lemon in two groups is drawn in both. A folded row in a group is hidden in
place rather than moved to the fold, and drawn there again when the fold is open.
"""

import dataclasses
from collections import Counter, abc

from .. import groups
from . import db, group_lead, order, parent_order


@dataclasses.dataclass(frozen=True)
class Header:
    group: groups.store.Group
    count: int  # rows in the group, drawn or not
    status_counts: tuple[tuple[str, int], ...] = ()
    active: int = 0  # rows in the group that aren't folded
    visible: int = 0  # rows actually drawn under the header

    @property
    def tally(self) -> str:
        members = len(self.group.members)
        return str(members) if self.visible == members else f"{self.visible}/{members}"

    @property
    def key(self) -> str:
        return f"group:{self.group.group_id}"


@dataclasses.dataclass(frozen=True)
class Row:
    key: str  # the notification id, then `@<group id>` for a row inside a group
    notification: db.Notification
    lead: bool = False  # the lead of the group this row is drawn under


def notification_id(key: str) -> int | None:
    """The notification a row key names, or None for a group header."""
    head = key.split("@", 1)[0]
    return int(head) if head.isdigit() else None


def row_group_id(key: str) -> int | None:
    """The group a lemon's row is drawn under, or None for a row in no group or a header."""
    _, at, rest = key.partition("@")
    return int(rest) if at and rest.isdigit() else None


def group_id(key: str) -> int | None:
    """The group a header's key names, or None for any other row."""
    prefix, _, rest = key.partition(":")
    return int(rest) if prefix == "group" and rest.isdigit() else None


def beside_their_lemons(
    rows: abc.Sequence[db.Notification],
    attached: abc.Mapping[str, str],
    lemons: abc.Sequence[db.Notification],
) -> list[db.Notification]:
    """*rows* with each attached row (a lemon item) right after its lemon, oldest first, and the
    rest in their order. A lemon an unread item needs, folded or hidden away, comes back from
    *lemons* where its first such item was, since the item is what wants your attention; a
    read item whose lemon isn't drawn isn't drawn either."""
    by_channel = {n.channel: n for n in lemons}
    present = {n.channel for n in rows if n.channel not in attached}
    items: dict[str, list[db.Notification]] = {}
    for n in rows:
        if n.channel in attached:
            items.setdefault(attached[n.channel], []).append(n)
    for lemon, theirs in list(items.items()):
        if lemon not in present and not any(n.is_unread for n in theirs):
            del items[lemon]
    result: list[db.Notification] = []
    for n in rows:
        lemon = attached.get(n.channel)
        if lemon is None:
            result.append(n)
            result.extend(items.pop(n.channel, []))
        elif lemon not in present and lemon in items:
            present.add(lemon)
            result.extend([by_channel[lemon]] if lemon in by_channel else [])
            result.extend(items.pop(lemon, []))
    return result


def layout(
    shown: abc.Sequence[db.Notification],
    folded: abc.Sequence[db.Notification],
    pinned: abc.Container[str],
    memberships: abc.Mapping[str, abc.Collection[str]],
    all_groups: abc.Sequence[groups.store.Group],
    statuses: abc.Mapping[str, str],
    kept: abc.Container[str] = (),
    fold_open: bool = False,
    deaf: abc.Container[str] = (),
    *,
    group_order: abc.Sequence[db.Notification] = (),
    ungrouped_first: bool = True,
    parents: abc.Mapping[str, str] | None = None,
    lead_first: bool = False,
    current: abc.Sequence[db.Notification] = (),
    empty_groups: bool = True,
    attached: abc.Mapping[str, str] | None = None,
) -> tuple[list[Header | Row], list[db.Notification]]:
    """The drawn list and what stays folded, from the inbox's *shown* and *folded* rows.

    *memberships* names each channel's groups; *all_groups* is every group, in order.
    A group with a row here, or a member in *current*, is drawn: when nothing is drawn
    under it its header still shows, so it can be reordered. A group with neither isn't drawn.
    Without *empty_groups* (a search), only a group with a row to draw is drawn.
    *kept* holds row keys drawn even inside a collapsed group or folded; a *deaf* lemon's
    rows are always drawn. *group_order* keeps group members in their order before
    folding, so pulling a focused row out of the fold doesn't move it in its group.
    With *lead_first*, a group's lead (see `group_lead.find`) sorts first in that group,
    above any pinned or deaf rows, and a drawn member pulls its ancestors in that group into
    the drawing unless the group is collapsed. It is a lead only in that group. *current* is every
    current session, so hiding or searching members away doesn't change who leads.
    *attached* maps a lemon item to its lemon: the row is drawn right after that lemon, brings
    the lemon back when it would be folded or hidden, and isn't counted in a header.
    """
    attached = attached or {}
    every = [*shown, *folded]
    positions = {n.id: i for i, n in enumerate(group_order)}
    every.sort(key=lambda n: positions.get(n.id, len(positions)))
    grouped = {
        group.name: [n for n in every if group.name in memberships.get(n.channel, ())]
        for group in all_groups
    }
    in_a_group = {n.channel for rows in grouped.values() for n in rows}
    folded_ids = {n.id for n in folded}

    def drawn(group: groups.store.Group) -> list[Header | Row]:
        rows = grouped[group.name]
        lemons = [n for n in rows if n.channel not in attached]
        members = [n for n in current if group.name in memberships.get(n.channel, ())] or lemons
        represented = Counter(statuses.get(n.channel, "") for n in members)
        lead = (
            group_lead.find(
                sorted(members, key=lambda n: positions.get(n.id, len(positions))),
                parents or {},
            )
            if lead_first
            else ""
        )
        shown_rows = [
            n
            for n in rows
            if n.channel in pinned
            or n.channel in deaf
            or f"{n.id}@{group.group_id}" in kept
            or (not group.collapsed and (fold_open or n.id not in folded_ids))
        ]
        # an unread item shows wherever its lemon is drawn, a pinned lemon in a collapsed
        # group included; an item the fold took stays folded, as it does outside a group
        drawn_lemons = {n.channel for n in shown_rows}
        shown_rows += [
            n
            for n in rows
            if n not in shown_rows
            and n.is_unread
            and n.id not in folded_ids
            and attached.get(n.channel) in drawn_lemons
        ]
        drawn_above = {
            above
            for n in shown_rows
            for above in group_lead.ancestors(n.channel, parents or {})
            if lead_first and not group.collapsed
        }
        visible = [
            *(n for n in rows if n in shown_rows or n.channel in drawn_above),
            *(
                n  # members the inbox hid away entirely come back for a drawn descendant
                for n in sorted(current, key=lambda n: positions.get(n.id, len(positions)))
                if n.channel in drawn_above
                and group.name in memberships.get(n.channel, ())
                and n.id not in {r.id for r in rows}
            ),
        ]
        pins = [n for n in visible if n.channel in pinned or n.channel in deaf]
        ordinary = parent_order.ordered(
            [n for n in visible if n.channel not in pinned and n.channel not in deaf],
            parents or {},
        )
        # the lead goes above the pins, whichever list it was in
        ordered = [n for n in visible if n.channel == lead] + [
            n for n in [*pins, *ordinary] if n.channel != lead
        ]
        ordered = beside_their_lemons(ordered, attached, [*rows, *members])
        return [
            Header(
                group,
                len(lemons),
                tuple(
                    (status, represented[status])
                    for status in order.band_names()
                    if status in represented and order.special_status(status)
                ),
                sum(n.id not in folded_ids for n in lemons),
                sum(n.channel not in attached for n in ordered),
            ),
            *(Row(f"{n.id}@{group.group_id}", n, n.channel == lead) for n in ordered),
        ]

    def shows_a_row(group: groups.store.Group) -> bool:
        """Whether anything goes under its header: a group folded away shows nothing."""
        return any(
            fold_open
            or n.id not in folded_ids
            or n.channel in pinned
            or n.channel in deaf
            or f"{n.id}@{group.group_id}" in kept
            for n in grouped[group.name]
        )

    def is_drawn(group: groups.store.Group) -> bool:
        if not empty_groups:
            return shows_a_row(group)

        return bool(grouped[group.name]) or any(
            group.name in memberships.get(n.channel, ()) for n in current
        )

    outside = [n for n in (every if fold_open else shown) if n.channel not in in_a_group]
    pins = {n.channel for n in outside if n.channel in pinned}
    by_a_pin = [n for n in outside if n.channel in pins or attached.get(n.channel) in pins]
    loose = beside_their_lemons(
        [n for n in outside if n not in by_a_pin], attached, [*every, *current]
    )
    entries: list[Header | Row] = [
        Row(str(n.id), n) for n in beside_their_lemons(by_a_pin, attached, [])
    ]
    ungrouped = [Row(str(n.id), n) for n in loose]
    if ungrouped_first:
        entries.extend(ungrouped)
    for group in all_groups:
        if is_drawn(group):
            entries.extend(drawn(group))
    if not ungrouped_first:
        entries.extend(ungrouped)

    drawn_outside = {n.channel for n in loose}
    return entries, [
        n for n in folded if n.channel not in in_a_group and n.channel not in drawn_outside
    ]
