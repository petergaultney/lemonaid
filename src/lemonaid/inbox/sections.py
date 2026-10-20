"""The inbox list cut into groups: each under a header line, in manual order.

Pinned rows in no group come first. The remaining rows in no group keep their
incoming order, before or after groups in their stored order.

A group is its header, its pinned and deaf rows, which stay when it's collapsed, and
unless it's collapsed the rest of its rows, bar any the caller keeps drawn. A
lemon in two groups is drawn in both. A folded row in a group is hidden in
place rather than moved to the fold, and drawn there again when the fold is open.
"""

import dataclasses
from collections import abc

from .. import groups
from . import db, order


@dataclasses.dataclass(frozen=True)
class Header:
    group: groups.store.Group
    count: int  # rows in the group, drawn or not
    band: str  # the most pressing of its rows' bands, as `order.band` names them; "" when empty
    unread: bool = False  # whether any of its rows is unread
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


def _band(rows: abc.Sequence[db.Notification], statuses: abc.Mapping[str, str]) -> str:
    return min(
        (order.band(statuses.get(n.channel, ""), n.is_unread, False) for n in rows),
        key=order.BAND_NAMES.index,
        default="",
    )


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
) -> tuple[list[Header | Row], list[db.Notification]]:
    """The drawn list and what stays folded, from the inbox's *shown* and *folded* rows.

    *memberships* names each channel's groups; *all_groups* is every group, in order.
    A group with no rows here isn't drawn, nor is one whose rows are all
    folded while the fold is closed: its header would have nothing to open.
    *kept* holds row keys drawn even inside a collapsed group or folded; a *deaf* lemon's
    rows are always drawn. *group_order* keeps group members in their order before
    folding, so pulling a focused row out of the fold doesn't move it in its group.
    """
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
        visible = [
            n
            for n in rows
            if n.channel in pinned
            or n.channel in deaf
            or f"{n.id}@{group.group_id}" in kept
            or (not group.collapsed and (fold_open or n.id not in folded_ids))
        ]
        return [
            Header(
                group,
                len(rows),
                _band(rows, statuses),
                any(n.is_unread for n in rows),
                sum(n.id not in folded_ids for n in rows),
                len(visible),
            ),
            *(
                Row(f"{n.id}@{group.group_id}", n)
                for n in [
                    *(n for n in rows if n.channel in pinned or n.channel in deaf),
                    *(
                        n
                        for n in rows
                        if n.channel not in pinned
                        and n.channel not in deaf
                        and (
                            f"{n.id}@{group.group_id}" in kept
                            or (not group.collapsed and (fold_open or n.id not in folded_ids))
                        )
                    ),
                ]
            ),
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

    entries: list[Header | Row] = [
        Row(str(n.id), n)
        for n in (every if fold_open else shown)
        if n.channel in pinned and n.channel not in in_a_group
    ]
    ungrouped = [
        Row(str(n.id), n)
        for n in (every if fold_open else shown)
        if n.channel not in in_a_group and n.channel not in pinned
    ]
    if ungrouped_first:
        entries.extend(ungrouped)
    for group in all_groups:
        if shows_a_row(group):
            entries.extend(drawn(group))
    if not ungrouped_first:
        entries.extend(ungrouped)

    return entries, [n for n in folded if n.channel not in in_a_group]
