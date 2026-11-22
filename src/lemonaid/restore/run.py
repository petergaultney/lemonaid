"""What restore and the front ends that bring lemons back share: a lemon to start, the
spot it goes to, and what restore asks of a terminal. Starting them is `starts`.
"""

import typing as ty
from collections import abc

from ..inbox import db
from . import launch, report


class Spot(ty.NamedTuple):
    where: str  # as a person names it
    was: str  # where its row recorded it, when that was taken; "" when it goes back there
    at: ty.Any  # the front end's own record of the spot, read only by that front end


class Relinked(ty.NamedTuple):
    lines: list[str]  # each row pointed at the pane its lemon runs in, as a person reads it
    json: list[dict]


class Lemon(ty.NamedTuple):
    row: db.Notification
    spot: Spot
    launch: launch.Launch
    lemon_id: str  # its brief's Lemon-ID, "" without a brief
    rearm: str  # the prompt that rearms its brief's waiters, "" when there are none
    note: str  # what to tell it about processes that died with the terminal, "" if none

    @property
    def channel(self) -> str:
        return self.row.channel


class Terminal(ty.NamedTuple):
    """What restore asks of the front end it brings lemons back into."""

    place: abc.Callable[
        [abc.Iterable[db.Notification]],
        tuple[list[tuple[db.Notification, Spot]], list[tuple[db.Notification, str]]],
    ]
    """(each lost row it can place, with its spot, in the order to make their windows; each
    row it can't, with why)."""
    reserve: abc.Callable[[abc.Sequence[tuple[Spot, str, str]]], None]
    """Make each spot's window ahead of its lemon, given its cwd and name, in the order
    given, so the layout comes back in that order whatever order the lemons start in."""
    release: abc.Callable[[Spot], None]  # close the window reserved for a lemon not started there
    open: abc.Callable[[Spot, str, abc.Mapping[str, str]], tuple[str, str]]
    """Open a spot's window, or take the one reserved for it: (the window, why not or "")."""
    type: abc.Callable[[str, str], str]  # type a line into the window made; why not, or ""
    close: abc.Callable[[str], None]  # close a window restore made, and only such a window
    running: abc.Callable[[abc.Sequence[Lemon]], set[str]]
    """The channels among these whose own process runs in its spot; their rows are
    pointed there."""
    seen: abc.Callable[[str], report.Seen]  # what the place a person names shows
    found: abc.Callable[[abc.Sequence[db.Notification], bool], set[str]]
    """The lost lemons among these that run somewhere now, started by hand; unless the
    flag (a dry run) is set, their rows are pointed there and are lost no longer."""
    relink: abc.Callable[[bool], Relinked]
    """Point every active row at the pane its lemon runs in (only report it, on a dry
    run); a lost lemon found running is lost no longer."""
    unready: abc.Callable[[db.Notification], str]
    """Why a running lemon's recorded place couldn't be restored after a crash, or ""."""
    strays: abc.Callable[[], list[str]]
    """Running lemons the inbox has no row for, as a person names them."""
    advice: str  # where a person learns more about lemons it couldn't restore
    up: abc.Callable[[], bool]
    """Whether the terminal runs now. A restore started from the inbox puts lemons back
    only into a running one, and never starts the terminal itself."""
