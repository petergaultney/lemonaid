"""Working out what `place toss` should tear down.

Teardown is session-first: the unit is a tmux session and the places it occupies.
That is the thing you can't already do with one command - `wt rm` releases a
directory and `:kill-session` closes a session, but nothing knows the two go
together, so tearing down by hand means remembering which worktrees a session
started and which session is hosting a worktree.

A key is a way of *naming* a session, not a separate mode: `toss <key>` finds the
session sitting in that place. Both forms then resolve to the same thing and act
on the whole set, so there is no form that kills a session while leaving places
it owned behind.

Problems come back as messages rather than being printed here, so the caller
decides how to report them.
"""

import typing as ty

from .. import tmux
from ..config import Config
from . import ownership


class TossTarget(ty.NamedTuple):
    session: str
    # Everything the session occupies and would release. Protected places are
    # already excluded by `ownership.places_of`. May be empty: a session with no
    # managed place is still a session, and closing it is legitimate.
    places: list[ownership.Place]
    # Is the caller's client attached to this session? Not the same as being in
    # its directory - you can cd into a place from a window belonging to another
    # session, in which case nothing needs switching away.
    from_inside: bool


def _refusal(config: Config, session: str) -> str:
    """Why *session* must not be torn down, if it must not be."""
    if not config.places.is_protected_session(session):
        return ""

    return (
        f"Session {session!r} is protected and will not be torn down. Long-lived "
        "catchall sessions aren't tied to one piece of work, so closing one loses "
        "windows rather than finishing something. Change `protected_sessions` "
        "under [places] if that is wrong."
    )


def _named(config: Config, key: str) -> tuple[TossTarget | None, str]:
    """The session sitting in the place *key* names."""
    place = ownership.find_place(config, key)
    if place is None:
        return None, f"No configured root has a directory for {key!r}"

    holding = ownership.sessions_holding(place.directory)
    if not holding:
        return None, f"No tmux session is in {place.directory}; nothing to tear down"

    if len(holding) > 1:
        return None, (
            f"{len(holding)} sessions have a window in {place.directory}: "
            + ", ".join(repr(s) for s in holding)
            + f". A key names a session, and {key!r} does not say which - so tearing "
            "one down here would be a guess. Attach to the one you mean and run "
            "`place toss` with no key."
        )

    session = holding[0]

    if refusal := _refusal(config, session):
        return None, refusal

    current, _ = tmux.navigation.get_current_location()

    return (
        TossTarget(session, ownership.places_of(session, config), session == current),
        "",
    )


def resolve_toss_target(config: Config, key: str | None) -> tuple[TossTarget | None, str]:
    """The session to tear down and what it owns, or why that can't be worked out.

    With a key, the session is found from the place - which works from anywhere,
    and is what a script or an agent should use. Without one, it is the session
    you are attached to.
    """
    if key is not None:
        return _named(config, key)

    current, _ = tmux.navigation.get_current_location()
    if not current:
        return None, "Not inside tmux, so there is no session here to tear down. Name one instead."

    if refusal := _refusal(config, current):
        return None, refusal

    return TossTarget(current, ownership.places_of(current, config), from_inside=True), ""
