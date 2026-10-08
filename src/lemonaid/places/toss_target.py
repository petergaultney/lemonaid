"""The workspace and optional directories a toss will retire."""

import typing as ty

from . import ownership


class TossTarget(ty.NamedTuple):
    # The session closed whole, or "" when none is: a place with no session, or
    # one held only by shared sessions.
    session: str
    # What is released: the place, unless it is protected (then nothing resolves).
    places: list[ownership.Place]
    # The place the toss was aimed at.
    place: ownership.Place | None
    # Every window of the closing session, with its panes as planned.
    session_windows: dict[str, list[ownership.Pane]]
    # Windows closed on their own, in sessions that survive, with their panes.
    partial: dict[str, list[ownership.Pane]]
    # Windows in protected sessions that sit in the place and are left as they
    # are, as 'session:@id'. They end up in a released directory.
    left_open: list[str]

    kept: tuple[str, ...] = ()

    @property
    def windows(self) -> list[str]:
        return list(self.session_windows)

    @property
    def closing(self) -> list[str]:
        return [*self.session_windows, *self.partial]
