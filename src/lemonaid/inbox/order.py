"""The order the inbox lists sessions in, the same in the wide table and the sidebar.

Pins come first. Below them, `alert` sessions, then `blocked`, then `running`,
then `merge`, then `review`, then `done` sessions, unread above read, then every
other unread session, then everything else read: `working`, `waiting`, and no
brief. Within each band rows
keep `db.get_active` order: pins by position, everything else unread first and
then newest first.

`fold` takes the rows of configured statuses out of that list, for the inbox
to show as one group at its bottom.
"""

from collections import abc

from . import db

_ALERT = 0
_BLOCKED = 1
_RUNNING = 2
_MERGE = 3
_REVIEW = 4
_UNREAD_DONE = 5
_DONE = 6
_UNREAD = 7  # working, waiting, or no brief
_READ = 8
_BANDS = {
    "alert": _ALERT,
    "blocked": _BLOCKED,
    "running": _RUNNING,
    "merge": _MERGE,
    "review": _REVIEW,
}


def _band(status: str, is_unread: bool) -> int:
    if status in _BANDS:
        return _BANDS[status]

    if status == "done":
        return _UNREAD_DONE if is_unread else _DONE

    return _UNREAD if is_unread else _READ


def by_status(
    rows: abc.Iterable[db.Notification],
    statuses: abc.Mapping[str, str],
    pinned: abc.Container[str],
) -> list[db.Notification]:
    """`rows`, in `db.get_active` order, with the unpinned ones moved into bands.

    The sort is stable, so pins and each band keep the order they came in.
    """
    return sorted(
        rows,
        key=lambda n: (
            -1 if n.channel in pinned else _band(statuses.get(n.channel, ""), n.is_unread)
        ),
    )


def fold(
    rows: abc.Iterable[db.Notification],
    statuses: abc.Mapping[str, str],
    pinned: abc.Container[str],
    folded_statuses: abc.Container[str],
) -> tuple[list[db.Notification], list[db.Notification]]:
    """`rows` split into the main list and the group folded at its bottom, order kept.

    A row folds when its brief status is in `folded_statuses`, unless it is
    pinned or unread: those stay where they would be without folding.
    """
    shown: list[db.Notification] = []
    folded: list[db.Notification] = []
    for n in rows:
        folds = (
            statuses.get(n.channel, "") in folded_statuses
            and n.channel not in pinned
            and not n.is_unread
        )
        (folded if folds else shown).append(n)
    return shown, folded
