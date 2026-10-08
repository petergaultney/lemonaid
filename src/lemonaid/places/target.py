"""Resolve a workspace first, with directory-only cleanup as a fallback."""

import os
from collections import abc
from pathlib import Path

from .. import tmux
from ..config import Config
from . import hooks, ownership, plan, session, workspace, workspace_purpose
from .toss_target import TossTarget


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

    panes = ownership.panes()
    planned = plan.plan_toss(
        place,
        panes,
        known if any(p.directory == place.directory for p in known) else [*known, place],
    )
    if planned.refusals:
        return None, "\n".join(planned.refusals)

    for candidate in planned.sessions:
        if config.places.is_protected_session(candidate.name):
            continue
        lemons = workspace_purpose.lemon_panes(candidate.name)
        if lemons is None:
            return (
                None,
                f"Could not inspect lemons in workspace {candidate.name!r}; nothing was closed",
            )
        if refusal := workspace.hybrid_refusal(candidate.name, panes, lemons, known):
            return None, refusal

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


def _here(config: Config, unattended: bool) -> tuple[TossTarget | None, str]:
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
    if key is None:
        current, _ = tmux.navigation.get_current_location()
        if current:
            if unattended:
                return None, (
                    f"This would close the session you are running in ({current!r}). "
                    f"An unattended toss has to name it: `place toss {current}`."
                )

            return workspace.resolve(config, current)

        return _here(config, unattended)

    if refusal := _session_refusal(config, key):
        return None, refusal

    if session.exists(key):
        return workspace.resolve(config, key)

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
        return (
            None,
            f"No configured root has a directory for {key!r}, and no tmux session has that name",
        )

    return _for_place(config, place)


def changed_since(
    config: Config, key: str | None, planned: TossTarget, unattended: bool = False
) -> str:
    """Reject changes to the closure or cleanup plan while confirmation was open."""
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
