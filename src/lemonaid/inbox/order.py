"""The order the inbox lists sessions in, the same in the wide table and the sidebar.

Pins come first. Below them, each configured status in rank order (by default `alert`,
then `blocked`, `running`, `merge`, `approve` and `review`), then `done` sessions, unread
above read, then every other unread session, then everything else read: a brief
without a status (`active`, `idle`, `deaf` or `dead`), and no brief. Within each band rows keep `db.get_active` order: pins
by position, everything else unread first and then newest first.

`fold` takes the rows a fold rule picks out of that list, for the inbox to show
as one group at its bottom: `fold_statuses` names the statuses that fold, and
attention mode names the ones that stay.
"""

from collections import abc

from .. import config, status_registry
from . import db

_TAIL = ("unread done", "done", "unread", "read")  # after the statuses' own bands


def band_names() -> tuple[str, ...]:
    """Every band in order: one per configured status but `done`, most urgent first, then
    unread done, done, every other unread row, and everything else read."""
    return (
        *(s.name for s in config.brief_statuses() if s.name != status_registry.DONE),
        *_TAIL,
    )


def _band(status: str, is_unread: bool, names: tuple[str, ...]) -> int:
    if status in names[: -len(_TAIL)]:
        return names.index(status)

    if status == status_registry.DONE:
        return names.index("unread done" if is_unread else "done")

    return names.index("unread" if is_unread else "read")


def band(status: str, is_unread: bool, is_pinned: bool) -> str:
    """The name of the band `by_status` puts a row in: "pinned", "alert", ... "read"."""
    names = band_names()
    return "pinned" if is_pinned else names[_band(status, is_unread, names)]


def special_status(status: str) -> bool:
    """Whether a brief status has its own inbox band, ahead of ordinary rows."""
    return status in status_registry.names(config.brief_statuses())


def by_status(
    rows: abc.Iterable[db.Notification],
    statuses: abc.Mapping[str, str],
    pinned: abc.Container[str],
) -> list[db.Notification]:
    """`rows`, in `db.get_active` order, with the unpinned ones moved into bands.

    The sort is stable, so pins and each band keep the order they came in.
    """
    names = band_names()
    return sorted(
        rows,
        key=lambda n: (
            -1 if n.channel in pinned else _band(statuses.get(n.channel, ""), n.is_unread, names)
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
