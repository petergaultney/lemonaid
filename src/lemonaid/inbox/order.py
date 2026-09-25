"""The order the inbox lists sessions in, the same in the wide table and the sidebar.

Pins come first. Below them, `blocked` sessions, then every other unread
session, then read `done` sessions, since a done lemon may have a PR ready to
merge, then everything else read: `working`, `waiting`, and no brief. Within
each band rows keep `db.get_active` order: pins by position, everything else
unread first and then newest first.
"""

from collections import abc

from . import db

_BLOCKED = 0
_UNREAD = 1
_DONE = 2
_READ = 3  # working, waiting, or no brief


def _band(status: str, is_unread: bool) -> int:
    if status == "blocked":
        return _BLOCKED

    if is_unread:
        return _UNREAD

    return _DONE if status == "done" else _READ


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
