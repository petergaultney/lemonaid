"""The order the inbox lists sessions in, the same in the wide table and the sidebar.

Pins come first. Below them, `alert` sessions, then `blocked`, then `running`,
then `merge`, then `approve`, then `review`, then `done` sessions, unread above
read, then every other unread session, then everything else read: a brief
without a status (`active`, `idle`, `deaf` or `dead`), and no brief. Within each band rows keep `db.get_active` order: pins
by position, everything else unread first and then newest first.

`fold` takes the rows a fold rule picks out of that list, for the inbox to show
as one group at its bottom: `fold_statuses` names the statuses that fold, and
attention mode names the ones that stay.
"""

from collections import abc

from . import db

_ALERT = 0
_BLOCKED = 1
_RUNNING = 2
_MERGE = 3
_APPROVE = 4
_REVIEW = 5
_UNREAD_DONE = 6
_DONE = 7
_UNREAD = 8  # a brief without a status, or no brief
_READ = 9
_BANDS = {
    "alert": _ALERT,
    "blocked": _BLOCKED,
    "running": _RUNNING,
    "merge": _MERGE,
    "approve": _APPROVE,
    "review": _REVIEW,
}


def _band(status: str, is_unread: bool) -> int:
    if status in _BANDS:
        return _BANDS[status]

    if status == "done":
        return _UNREAD_DONE if is_unread else _DONE

    return _UNREAD if is_unread else _READ


BAND_NAMES = (
    "alert",
    "blocked",
    "running",
    "merge",
    "approve",
    "review",
    "unread done",
    "done",
    "unread",
    "read",
)


def band(status: str, is_unread: bool, is_pinned: bool) -> str:
    """The name of the band `by_status` puts a row in: "pinned", "alert", ... "read"."""
    return "pinned" if is_pinned else BAND_NAMES[_band(status, is_unread)]


def special_status(status: str) -> bool:
    """Whether a brief status has its own inbox band, ahead of ordinary rows."""
    return status in _BANDS or status == "done"


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


FoldRule = abc.Callable[[str, bool], bool]  # whether a row of this status, unread or not, folds


def status_rule(folded_statuses: abc.Collection[str]) -> FoldRule | None:
    """Fold a read row whose status is in *folded_statuses*; None when nothing folds."""
    if not folded_statuses:
        return None

    return lambda status, is_unread: status in folded_statuses and not is_unread


def attention_rule(attention_statuses: abc.Container[str]) -> FoldRule:
    """Fold every row whose status is not in *attention_statuses*, read or unread."""
    return lambda status, is_unread: status not in attention_statuses


def fold(
    rows: abc.Iterable[db.Notification],
    statuses: abc.Mapping[str, str],
    pinned: abc.Container[str],
    folds: FoldRule | None,
    in_view: abc.Container[str],
    deaf: abc.Container[str],
    hidden: abc.Container[str] = (),
) -> tuple[list[db.Notification], list[db.Notification]]:
    """`rows` split into the main list and the group folded at its bottom, order kept.

    A row folds when *folds* says so for its brief status, unless it is pinned,
    deaf, or its channel is `in_view`: those stay where they would be without
    folding. A `hidden` channel folds the same way, read or unread.
    """
    shown: list[db.Notification] = []
    folded: list[db.Notification] = []
    for n in rows:
        folds_here = (
            n.channel not in pinned
            and n.channel not in in_view
            and n.channel not in deaf
            and (
                n.channel in hidden
                or (folds is not None and folds(statuses.get(n.channel, ""), n.is_unread))
            )
        )
        (folded if folds_here else shown).append(n)
    return shown, folded
