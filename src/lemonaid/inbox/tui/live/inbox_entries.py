"""The inbox's rows in drawing order: group headers and lemons, or a search's matches."""

from collections import abc

from ... import db, sections, view
from . import inbox_frame

Entry = sections.Header | sections.Row


def _focused_keys(frame: inbox_frame.Frame) -> set[str]:
    return {
        f"{n.id}@{group.group_id}"
        for n in frame.active.rows
        if n.channel in frame.focused_channels
        for group in frame.groups
        if group.name in frame.active.memberships.get(n.channel, ())
    }


def entries(
    frame: inbox_frame.Frame,
    shown: list[db.Notification],
    folded: list[db.Notification],
    kept: abc.Set[str],
    fold_open: bool,
    group_order: abc.Sequence[db.Notification] = (),
    *,
    ungrouped_first: bool = True,
    parents_first: bool = True,
    lead_first: bool = False,
) -> tuple[list[Entry], list[db.Notification], list[db.Notification]]:
    """The main table's entries, the rows still folded away, and the other-terminal rows.

    A search draws only its matches, under their groups; otherwise rows sit under their
    groups, and an open fold restores its rows in place.
    """
    if frame.matching_ids is not None:
        matching = frame.matching_ids
        found = [n for n in [*shown, *folded] if n.id in matching]
        laid_out, _ = sections.layout(
            found,
            [],
            frame.pinned,
            frame.active.memberships,
            frame.groups,
            view.statuses(frame.active.cards, frame.active.rows),
            {
                f"{n.id}@{group.group_id}"
                for group in frame.groups
                for n in found
                if group.name in frame.active.memberships.get(n.channel, ())
            },
            True,
            frame.active.deaf,
            group_order=group_order,
            ungrouped_first=ungrouped_first,
            parents=frame.parents if parents_first else {},
            lead_first=lead_first,
            current=frame.active.rows,
        )
        return (
            laid_out,
            folded,
            [n for n in frame.other if n.id in matching],
        )

    laid_out, folded = sections.layout(
        shown,
        folded,
        frame.pinned,
        frame.active.memberships,
        frame.groups,
        view.statuses(frame.active.cards, frame.active.rows),
        {*kept, *_focused_keys(frame)},
        fold_open,
        frame.active.deaf,
        group_order=group_order,
        ungrouped_first=ungrouped_first,
        parents=frame.parents if parents_first else {},
        lead_first=lead_first,
        current=frame.active.rows,
    )
    return laid_out, folded, frame.other
