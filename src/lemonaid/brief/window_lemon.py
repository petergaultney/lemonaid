"""The lemons a tmux window holds, as the inbox records them, and their brief.

The scratch pane's brief belongs to the lemon in the window the pane is in; this
is how the pane checks which one that is.
"""

from ..front_end import location
from ..inbox import db, emoji
from . import attached, target


def _in(notification: db.Notification, tmux_session: str, index: str) -> bool:
    where = location.of(notification.metadata, notification.switch_source)
    return where.front_end == "tmux" and (where.workspace, where.slot) == (tmux_session, index)


def find(here: str) -> tuple[target.Target, list[int]] | None:
    """The brief of the lemons recorded in *here* (`session:index`) and their row ids,
    or None when no active row is in that window."""
    tmux_session, _, index = here.partition(":")
    with db.connect(timeout=db.UI_TIMEOUT_SECONDS) as conn:
        rows = db.get_active(conn)
        in_window = [n for n in rows if _in(n, tmux_session, index)]
        if not tmux_session or not in_window:
            return None

        found = target.for_session(
            tmux_session, rows, attached.for_rows(conn, rows), index, emoji.by_channel(conn)
        )

    return found, [n.id for n in in_window]


def _lemons(found: target.Target) -> tuple:
    lemon = found.lemon
    return (
        found.attached,
        found.dirs,
        found.place,
        found.names,
        (lemon.tmux_session, lemon.tmux_window) if lemon else None,
        tuple(_lemons(member) for member in found.members),
    )


def same_lemons(a: target.Target, b: target.Target) -> bool:
    """Whether *a* and *b* are for the same lemons, whose briefs they look for in the same
    places, however their emoji or other display details have changed."""
    return _lemons(a) == _lemons(b)
