"""The order the inbox lists sessions in, the same in the wide table and the sidebar.

Pins come first. Below them, `alert` sessions, then `blocked`, then `merge`,
then `done` sessions, unread above read, then every other unread session, then
everything else read: `working`, `waiting`, and no brief. Within each band rows
keep `db.get_active` order: pins by position, everything else unread first and
then newest first.
"""

from collections import abc

from . import db

_ALERT = 0
_BLOCKED = 1
_MERGE = 2
_UNREAD_DONE = 3
_DONE = 4
_UNREAD = 5  # working, waiting, or no brief
_READ = 6  # working, waiting, or no brief
_BANDS = {"alert": _ALERT, "blocked": _BLOCKED, "merge": _MERGE}


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
