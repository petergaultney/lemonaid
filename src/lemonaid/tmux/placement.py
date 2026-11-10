"""Where each lost lemon goes back: its recorded window, or the next free one.

Pure: it takes the live layout as an argument, so the plan can be shown before
anything is started. A session that already runs gains the windows it is missing
and nothing in it is touched; a lemon whose recorded window is taken, by a live
window or by another lemon recorded in the same one, gets the next free index.
"""

import typing as ty
from collections import abc

from ..inbox import db


class Spot(ty.NamedTuple):
    session: str
    index: int
    creates_session: bool  # the first window of a session that doesn't run now
    recorded: int  # the index the row recorded; differs from `index` when it was taken


def _recorded(row: db.Notification) -> tuple[str, int] | None:
    session, window = row.metadata.get("tmux_session"), row.metadata.get("tmux_window")
    try:
        return (str(session), int(window)) if session and window is not None else None
    except (TypeError, ValueError):
        return None


def _session_order(row: db.Notification) -> tuple[int, ...]:
    match row.metadata.get("tmux_session_order"):
        case [int(created), int(started), int(number)]:
            return (0, created, started, number)
        case _:
            return (1,)


def place(
    rows: abc.Iterable[db.Notification], live: abc.Mapping[str, abc.Set[int]]
) -> tuple[list[tuple[db.Notification, Spot]], list[db.Notification]]:
    """(each placeable row with its spot, in the order to start them; the rows with no
    recorded window).

    The lemon heard from most recently keeps a contested window. Sessions start in the
    order tmux made them, and windows by index, so a new session's first window is the
    one that creates it.
    """
    recent_first = sorted(rows, key=lambda r: max(r.created_at, r.turn_at or 0.0), reverse=True)
    unplaced = [row for row in recent_first if _recorded(row) is None]
    taken = {session: set(indices) for session, indices in live.items()}
    spots: list[tuple[db.Notification, Spot]] = []
    for row in recent_first:
        if (recorded := _recorded(row)) is None:
            continue

        session, index = recorded
        used = taken.setdefault(session, set())
        free = next(i for i in range(index, index + len(used) + 1) if i not in used)
        used.add(free)
        spots.append((row, Spot(session, free, False, index)))

    order = {}
    for row, spot in spots:
        order[spot.session] = min(order.get(spot.session, (2,)), _session_order(row))
    spots.sort(key=lambda pair: (order[pair[1].session], pair[1].session, pair[1].index))

    seen: set[str] = set(live)
    placed = []
    for row, spot in spots:
        placed.append((row, spot._replace(creates_session=spot.session not in seen)))
        seen.add(spot.session)

    return placed, unplaced
