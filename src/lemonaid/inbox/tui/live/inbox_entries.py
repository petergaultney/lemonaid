"""The inbox's rows in drawing order: group headers and lemons, or a search's matches."""

from collections import abc

from ... import db, sections, view
from . import inbox_frame

Entry = sections.Header | sections.Row


def entries(
    frame: inbox_frame.Frame,
    shown: list[db.Notification],
    folded: list[db.Notification],
    kept: abc.Set[str],
    fold_open: bool,
    group_order: abc.Sequence[db.Notification] = (),
    *,
    ungrouped_first: bool = True,
) -> tuple[list[Entry], list[db.Notification], list[db.Notification]]:
    """The main table's entries, the rows still folded away, and the other-terminal rows.

    A search draws only its matches, under their groups; otherwise rows sit under their
    groups, and an open fold draws its rows after everything else.
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
        kept,
        fold_open,
        frame.active.deaf,
        group_order=group_order,
        ungrouped_first=ungrouped_first,
    )
    if fold_open:
        laid_out = [*laid_out, *(sections.Row(str(n.id), n) for n in folded)]
    return laid_out, folded, frame.other
