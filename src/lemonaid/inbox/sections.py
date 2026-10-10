"""The inbox list cut into groups: each under a header line, in the groups' own order.

Pinned rows in no group come first. The rest of the rows in no group keep the
order they arrived in, and each group goes just above the first of them whose
band is no more pressing than the group's own: its most pressing row's. So a
group holding a `blocked` lemon sits at the top of the `blocked` rows, and
groups in the same band keep their own order.

A group is its header, its pinned rows, which stay when it's collapsed, and
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

    @property
    def tally(self) -> str:
        """`3`, or `2/3` when some of the group's rows are folded."""
        return str(self.count) if self.active == self.count else f"{self.active}/{self.count}"

    @property
    def key(self) -> str:
        return f"group:{self.group.group_id}"


@dataclasses.dataclass(frozen=True)
class Row:
    key: str  # the notification id, then `@<group id>` for a row inside a group
    notification: db.Notification


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


def _band(rows: abc.Sequence[db.Notification], statuses: abc.Mapping[str, str]) -> str:
    return min(
        (order.band(statuses.get(n.channel, ""), n.is_unread, False) for n in rows),
        key=order.BAND_NAMES.index,
        default="",
    )


def _rank(band: str) -> int:
    """Where a band sorts; an empty group's "" sorts after every band."""
    return order.BAND_NAMES.index(band) if band in order.BAND_NAMES else len(order.BAND_NAMES)


def layout(
    shown: abc.Sequence[db.Notification],
    folded: abc.Sequence[db.Notification],
    pinned: abc.Container[str],
    memberships: abc.Mapping[str, abc.Collection[str]],
    all_groups: abc.Sequence[groups.store.Group],
    statuses: abc.Mapping[str, str],
    kept: abc.Container[str] = (),
    fold_open: bool = False,
) -> tuple[list[Header | Row], list[db.Notification]]:
    """The drawn list and what stays folded, from the inbox's *shown* and *folded* rows.

    *memberships* names each channel's groups; *all_groups* is every group, in order.
    A group with no rows here isn't drawn.
    *kept* holds row keys drawn even inside a collapsed group or folded.
    """
    every = [*shown, *folded]
    grouped = {
        group.name: [n for n in every if group.name in memberships.get(n.channel, ())]
        for group in all_groups
    }
    in_a_group = {n.channel for rows in grouped.values() for n in rows}
    folded_ids = {n.id for n in folded}

    def drawn(group: groups.store.Group) -> list[Header | Row]:
        rows = grouped[group.name]
        return [
            Header(
                group,
                len(rows),
                _band(rows, statuses),
                any(n.is_unread for n in rows),
                sum(n.id not in folded_ids for n in rows),
            ),
            *(
                Row(f"{n.id}@{group.group_id}", n)
                for n in [
                    *(n for n in rows if n.channel in pinned),
                    *(
                        n
                        for n in rows
                        if n.channel not in pinned
                        and (
                            f"{n.id}@{group.group_id}" in kept
                            or (not group.collapsed and (fold_open or n.id not in folded_ids))
                        )
                    ),
                ]
            ),
        ]

    pending = sorted(
        (group for group in all_groups if grouped[group.name]),
        key=lambda g: _rank(_band(grouped[g.name], statuses)),
    )  # stable, so groups in one band keep their order
    entries: list[Header | Row] = [
        Row(str(n.id), n) for n in shown if n.channel in pinned and n.channel not in in_a_group
    ]
    for n in shown:
        if n.channel in in_a_group or n.channel in pinned:
            continue

        rank = _rank(order.band(statuses.get(n.channel, ""), n.is_unread, False))
        while pending and _rank(_band(grouped[pending[0].name], statuses)) <= rank:
            entries.extend(drawn(pending.pop(0)))
        entries.append(Row(str(n.id), n))

    for group in pending:
        entries.extend(drawn(group))

    return entries, [n for n in folded if n.channel not in in_a_group]
