"""Working out what `place toss` should tear down.

Teardown is place-first: the unit is a managed directory, and what closes with
it is whatever tmux has sitting in it. Bare `toss` starts from the directory you
are standing in; `toss <key>` names one from anywhere. A session closes along
with the place only when it is dedicated to that place - named for it, or
entirely inside it, and holding no other managed place. In a session that holds
other places as well, only the windows sitting in this one close.

Named `toss` can close an exact session when the name has no existing or listed
place. Bare `toss` never falls back to the session the caller is in. A directory that
resolves to no place is a refusal, not a session to kill: the one time that
fallback ran, it closed the session of the lemon that ran it.

Problems come back as messages rather than being printed here, so the caller
decides how to report them.
"""

import os
import typing as ty
from collections import abc
from pathlib import Path

from .. import tmux
from ..config import Config
from . import hooks, ownership, plan, session


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

    @property
    def windows(self) -> list[str]:
        return list(self.session_windows)

    @property
    def closing(self) -> list[str]:
        return [*self.session_windows, *self.partial]


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

    session = dedicated[0] if dedicated else None
    if session and (refusal := _session_refusal(config, session.name)):
        return None, refusal

    # A protected session is hands-off one window at a time too: its windows in
    # the place stay, and the person is told they now sit in a released directory.
    shared = [s for s in planned.sessions if not s.dedicated]
    protected = {s.name for s in shared if config.places.is_protected_session(s.name)}
    return TossTarget(
        session.name if session else "",
        [place],
        place,
        {window: planned.panes_of(window) for window in session.windows} if session else {},
        {
            window: planned.panes_of(window)
            for s in shared
            if s.name not in protected
            for window in s.tied
        },
        [f"{s.name}:{window}" for s in shared if s.name in protected for window in s.tied],
    ), ""


def _for_session(
    config: Config, name: str, known: list[ownership.Place]
) -> tuple[TossTarget | None, str]:
    """A named tmux session with no managed directory behind it."""
    if refusal := _session_refusal(config, name):
        return None, refusal

    windows, why_not = session.inspect(name, known)
    if windows is None:
        return None, why_not

    return TossTarget(name, [], None, windows, {}, []), ""


def _here(config: Config, unattended: bool) -> tuple[TossTarget | None, str]:
    """Bare `toss`: the place the current directory is in, and nothing else.

    The caller's own tmux session is never a fallback target. It closes only
    when the directory resolved to a place that session is dedicated to, and
    an unattended caller (`--yes` or `--json`) has to name even that: a lemon
    tearing down its own session should say so. Not knowing which session the
    caller is in counts as it being this one.
    """
    cwd = Path(os.getcwd())
    known = ownership.managed_places(config)
    place = ownership.place_at(cwd, known)
    if place is None:
        root = config.places.root_for(cwd)
        where = (
            f"{cwd} is under the root {root.path}, but is not a place that root lists"
            if root
            else f"{cwd} is not inside any managed place"
        )
        return (
            None,
            f"{where}, so there is nothing here to tear down. Name one: `place toss <key>`.",
        )

    doomed, why_not = _for_place(config, place)
    if doomed is None:
        return None, why_not

    if not (unattended and doomed.session):
        return doomed, ""

    current, _ = tmux.navigation.get_current_location()
    if current is None:
        return None, (
            f"This would close session {doomed.session!r}, and whether that is the one you are "
            f"running in can't be told (no TMUX_PANE). An unattended toss has to name it: "
            f"`place toss {place.key}`."
        )

    if doomed.session == current:
        return None, (
            f"This would close the session you are running in ({current!r}). An unattended "
            f"toss has to say so: `place toss {place.key}`."
        )

    return doomed, ""


def resolve_toss_target(
    config: Config, key: str | None, unattended: bool = False
) -> tuple[TossTarget | None, str]:
    """What to tear down and what closes with it, or why that can't be worked out.

    With a key, the place is found by name - which works from anywhere, and is
    what a script or an agent should use. Without one, it is the place the
    current directory is in; *unattended* (`--yes` or `--json`) says no one is
    at a prompt, which tightens what a bare toss may do to the caller's own
    session.
    """
    if key is None:
        return _here(config, unattended)

    known = ownership.managed_places_checked(config)
    if known is None:
        return None, "Could not list managed places; nothing was closed"

    place = next((place for place in known if place.key == key), None)
    if place is None:
        for root in config.places.roots:
            directory, checked = hooks.directory_for_key_checked(root, key)
            if not checked:
                return None, f"Could not resolve {key!r} under {root.path}; nothing was closed"

            if directory is not None:
                place = ownership.Place(key, root, directory)
                break

    if place is None:
        return _for_session(config, key, known)

    return _for_place(config, place)


def changed_since(
    config: Config, key: str | None, planned: TossTarget, unattended: bool = False
) -> str:
    """Why *planned* no longer describes tmux, or "" when it still does.

    The confirmation prompt sits between planning and teardown for as long as
    the person takes. So the plan is made again from a fresh snapshot, and any
    difference - a pane that moved, a window split or opened in the place, a
    session that gained a window - stops the toss: it is work the person never
    saw in the confirmation.
    """
    now, why_not = resolve_toss_target(config, key, unattended)
    if now is None:
        return f"{why_not}\nThat changed since the plan was made; nothing was closed."

    if now == planned:
        return ""

    was, is_now = set(planned.closing), set(now.closing)
    if is_now - was:
        detail = f"windows {', '.join(sorted(is_now - was))} appeared"
    elif was - is_now:
        detail = f"windows {', '.join(sorted(was - is_now))} are gone"
    else:
        detail = "a pane moved or was added"

    return f"The layout changed since the plan was made ({detail}); nothing was closed."
