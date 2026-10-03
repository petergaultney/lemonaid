"""Working out what `place toss` should tear down.

Teardown is place-first: the unit is a managed directory, and what closes with
it is whatever tmux has sitting in it. Bare `toss` starts from the directory you
are standing in; `toss <key>` names one from anywhere. A session closes along
with the place only when it is dedicated to that place - named for it, or
entirely inside it, and holding no other managed place.

A session that holds other places as well is shared, and this release refuses
to touch it: closing just the windows in the place is the next step, and until
then the message says which windows those are.

Problems come back as messages rather than being printed here, so the caller
decides how to report them.
"""

import os
import typing as ty
from collections import abc
from pathlib import Path

from .. import tmux
from ..config import Config
from . import ownership, plan


class TossTarget(ty.NamedTuple):
    # Empty when nothing is killed: a place with no session, which is the
    # simple case rather than an error.
    session: str
    # What is released. Protected places never appear; a session with no managed
    # place leaves this empty, and closing it is still legitimate.
    places: list[ownership.Place]
    # The place the toss was aimed at, or None for a session that is just a session.
    place: ownership.Place | None
    # The windows that close: every window of a closing session.
    windows: list[str]
    # Windows elsewhere that sit in the place and are left as they are, as
    # 'session:@id'. They end up in a released directory.
    left_open: list[str]


def _session_refusal(config: Config, session: str) -> str:
    """Why *session* must not be torn down, if it must not be."""
    if not config.places.is_protected_session(session):
        return ""

    return (
        f"Session {session!r} is protected and will not be torn down. Long-lived "
        "catchall sessions aren't tied to one piece of work, so closing one loses "
        "windows rather than finishing something. Change `protected_sessions` "
        "under [places] if that is wrong."
    )


def _place_refusal(place: ownership.Place, known: abc.Sequence[ownership.Place]) -> str:
    """Why *place* must not be released, if it must not be.

    A place containing other managed places is refused whatever their state: the
    destroy hook is opaque, so releasing the outer directory may well take the
    inner ones with it.
    """
    if place.root.is_protected(place.key):
        return (
            f"{place.key!r} is protected and will not be released. Change `protected` "
            f"for {place.root.path} under [[places.roots]] if that is wrong."
        )

    outer = place.directory.resolve()
    inside = sorted(p.key for p in known if outer in p.directory.resolve().parents)
    if inside:
        return (
            f"{place.key!r} contains {', '.join(repr(k) for k in inside)}, and releasing "
            "it could take them too. Toss those first."
        )

    return ""


def _shared(planned: plan.Plan) -> str:
    """Why a place held only by shared sessions is not touched yet."""
    lines = [
        f"{s.name!r} also holds {', '.join(repr(k) for k in s.other_places)}, so it is not "
        f"closed with {planned.place.key!r}. Its windows in {planned.place.key!r}: "
        + ", ".join(s.tied)
        if s.other_places
        else f"{s.name!r} has windows outside {planned.place.key!r} as well, so it is not "
        f"closed with it. Its windows in {planned.place.key!r}: " + ", ".join(s.tied)
        for s in planned.sessions
    ]

    return "\n".join(
        [
            *lines,
            "Closing just those windows is not implemented yet. Close them yourself and "
            f"run `place toss {planned.place.key}` again to release the directory.",
        ]
    )


def _for_place(config: Config, place: ownership.Place) -> tuple[TossTarget | None, str]:
    """What closes with *place*, given where tmux's panes are right now."""
    known = ownership.managed_places(config)
    if refusal := _place_refusal(place, known):
        return None, refusal

    planned = plan.plan_toss(
        place,
        ownership.panes(),
        known if any(p.directory == place.directory for p in known) else [*known, place],
    )
    if planned.refusals:
        return None, "\n".join(planned.refusals)

    dedicated = [s for s in planned.sessions if s.dedicated]
    if len(dedicated) > 1:
        return None, (
            f"{len(dedicated)} sessions are each entirely in {place.key!r}: "
            + ", ".join(repr(s.name) for s in dedicated)
            + ". Close one of them yourself, then run this again."
        )

    if not dedicated and planned.sessions:
        return None, _shared(planned)

    session = dedicated[0] if dedicated else None
    if session and (refusal := _session_refusal(config, session.name)):
        return None, refusal

    return TossTarget(
        session.name if session else "",
        [place],
        place,
        session.windows if session else [],
        [f"{s.name}:{window}" for s in planned.sessions if not s.dedicated for window in s.tied],
    ), ""


def _here(config: Config) -> tuple[TossTarget | None, str]:
    """Bare `toss`: the place the current directory is in, else the current session.

    A session holding no managed place is just a session, and closing it is a
    fine thing to ask for from anywhere in it. One that does hold places needs
    to be told which, since the current directory did not say.
    """
    known = ownership.managed_places(config)
    if (place := ownership.place_at(Path(os.getcwd()), known)) is not None:
        return _for_place(config, place)

    current, _ = tmux.navigation.get_current_location()
    if not current:
        return None, (
            "Not inside a managed place or a tmux session, so there is nothing here "
            "to tear down. Name a place instead."
        )

    if refusal := _session_refusal(config, current):
        return None, refusal

    if held := ownership.places_of(current, config, known):
        return None, (
            f"The current directory is not in a managed place, and {current!r} holds "
            + ", ".join(repr(p.key) for p in held)
            + ". Name the one you mean: `place toss <key>`."
        )

    return TossTarget(
        current, [], None, sorted({p.window for p in ownership.panes() if p.session == current}), []
    ), ""


def resolve_toss_target(config: Config, key: str | None) -> tuple[TossTarget | None, str]:
    """What to tear down and what closes with it, or why that can't be worked out.

    With a key, the place is found by name - which works from anywhere, and is
    what a script or an agent should use. Without one, it is the place the
    current directory is in.
    """
    if key is None:
        return _here(config)

    place = ownership.find_place(config, key)
    if place is None:
        return None, f"No configured root has a directory for {key!r}"

    return _for_place(config, place)
