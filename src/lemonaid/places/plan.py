"""What a toss aimed at one place would close, worked out from a pane snapshot.

The unit of work is a place, and tmux windows are what sit in it. A window is
tied to the place when every pane in it is there; a session is dedicated to the
place when the place is all it holds. Both are read off the panes tmux reports,
so this module takes the snapshot as an argument and decides nothing else.
"""

import typing as ty
from collections import abc

from ..tmux import session as tmux_session
from . import ownership


class SessionPlan(ty.NamedTuple):
    name: str
    tied: list[str]  # windows whose every pane is in the place
    mixed: list[str]  # windows with a pane in the place and a pane elsewhere
    other: list[str]  # windows with no pane in the place
    other_places: list[str]  # keys of other unprotected places this session's panes sit in
    dedicated: bool  # closing the whole session is closing the place

    @property
    def windows(self) -> list[str]:
        return [*self.tied, *self.mixed, *self.other]


class Plan(ty.NamedTuple):
    place: ownership.Place
    sessions: list[SessionPlan]  # every session with a pane in the place, by name
    refusals: list[str]  # why nothing should happen, one per mixed window


_Located = dict[str, ownership.Place | None]  # pane ID -> the place it sits in


def _in(pane: ownership.Pane, place: ownership.Place, at: _Located) -> bool:
    found = at[pane.pane]

    return found is not None and found.directory.resolve() == place.directory.resolve()


def _by_window(panes: abc.Iterable[ownership.Pane]) -> dict[tuple[str, str], list[ownership.Pane]]:
    grouped: dict[tuple[str, str], list[ownership.Pane]] = {}
    for pane in panes:
        grouped.setdefault((pane.session, pane.window), []).append(pane)

    return grouped


def _describe_mixed(
    window: str, panes: abc.Sequence[ownership.Pane], place: ownership.Place, at: _Located
) -> str:
    inside = [p.pane for p in panes if _in(p, place, at)]
    outside = [
        f"{p.pane} at {p.path}" if p.path else f"{p.pane} (no path)"
        for p in panes
        if not _in(p, place, at)
    ]

    return (
        f"Window {window} in {panes[0].session!r} has {', '.join(inside)} in {place.key!r} "
        f"and {', '.join(outside)} elsewhere. Closing the window would take both, so "
        "move or close one of them first."
    )


def _session_plan(
    name: str,
    windows: abc.Mapping[str, abc.Sequence[ownership.Pane]],
    place: ownership.Place,
    at: _Located,
) -> SessionPlan:
    tied, mixed, other = [], [], []
    for window, panes in windows.items():
        inside = [_in(p, place, at) for p in panes]
        if all(inside):
            tied.append(window)
        elif any(inside):
            mixed.append(window)
        else:
            other.append(window)

    other_places = sorted(
        {
            found.key
            for panes in windows.values()
            for p in panes
            if (found := at[p.pane]) is not None
            and not _in(p, place, at)
            and not found.root.is_protected(found.key)
        }
    )

    # A session named for the place was opened for it, so stray windows at
    # unmanaged paths go with it, as they always have. Any other session has to
    # be entirely in the place. Either way, a second managed place means the
    # session is shared, and closing it would take that place's work too.
    dedicated = (
        bool(tied)
        and not mixed
        and not other_places
        and (tmux_session.sanitize_name(place.key) == name or not other)
    )

    return SessionPlan(name, tied, mixed, other, other_places, dedicated)


def plan_toss(
    place: ownership.Place,
    panes: abc.Iterable[ownership.Pane],
    places: abc.Sequence[ownership.Place],
) -> Plan:
    """Classify every window and session that sits in *place*.

    *places* must include *place* itself, since each pane is assigned to the most
    specific managed place containing it, and nesting is resolved there.
    """
    all_panes = list(panes)
    at: _Located = {
        pane.pane: ownership.place_at(pane.path, places) if pane.path else None
        for pane in all_panes
    }
    grouped = _by_window(all_panes)
    involved = sorted({p.session for p in all_panes if _in(p, place, at)})

    sessions = [
        _session_plan(
            name,
            {window: panes for (s, window), panes in grouped.items() if s == name},
            place,
            at,
        )
        for name in involved
    ]
    refusals = [
        _describe_mixed(window, grouped[(session.name, window)], place, at)
        for session in sessions
        for window in session.mixed
    ]

    return Plan(place, sessions, refusals)
