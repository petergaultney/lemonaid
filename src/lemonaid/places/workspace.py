"""Session teardown with optional, exclusive directory cleanup."""

from collections import abc

from ..config import Config
from ..tmux import session
from . import hooks, ownership, workspace_purpose
from .toss_target import TossTarget


def _kept_reason(
    place: ownership.Place,
    name: str,
    panes: abc.Sequence[ownership.Pane],
    known: abc.Sequence[ownership.Place],
) -> str:
    directory = place.directory.resolve()
    if place.root.is_protected(place.key):
        return "protected directory"

    if not place.root.destroy:
        return "no destroy hook"

    if any(pane.path is None for pane in panes):
        return "a pane's directory is unknown"

    if any(
        pane.session != name
        and pane.path is not None
        and pane.path.resolve().is_relative_to(directory)
        for pane in panes
    ):
        return "used by another workspace"

    if any(directory in other.directory.resolve().parents for other in known):
        return "contains another managed directory"

    return ""


def hybrid_refusal(
    name: str, panes: list[ownership.Pane], lemons: set[str], known: list[ownership.Place]
) -> str:
    paths = []
    managed = set()
    for pane in panes:
        if pane.session != name or pane.pane not in lemons:
            continue
        if pane.path is None:
            return f"Could not identify a lemon's place in workspace {name!r}; nothing was closed"
        place = ownership.place_at(pane.path, known)
        if place:
            managed.add(place.directory.resolve())
        else:
            paths.append(pane.path.resolve())
    # An ancestor cwd alone does not establish a shared place: nested managed
    # directories may be separate jobs, especially when discovery failed.
    purposes = managed | set(paths)
    if len(purposes) > 1:
        directories = ", ".join(str(path) for path in sorted(purposes))
        return f"Workspace {name!r} is hybrid and is not a managed place; nothing was closed. Lemons occupy: {directories}"
    return ""


def _directories(
    config: Config, name: str, panes: list[ownership.Pane], lemons: set[str]
) -> tuple[list[ownership.Place], list[str], str]:
    known = ownership.managed_places_checked(config)
    if known is None:
        return (
            [],
            ["Directory discovery failed; no directories will be released"],
            hybrid_refusal(name, panes, lemons, []),
        )

    # A session opened for a directory still belongs to it after its shells cd away.
    for root in config.places.roots:
        directory, checked = hooks.directory_for_key_checked(root, name)
        if not checked:
            if not any(
                place.root == root and session.sanitize_name(place.key) == name for place in known
            ) and not any(
                pane.session == name
                and pane.path is not None
                and pane.path.resolve().is_relative_to(root.path.resolve())
                for pane in panes
            ):
                continue

            return (
                [],
                [f"Directory lookup failed under {root.path}; no directories will be released"],
                hybrid_refusal(name, panes, lemons, known),
            )

        if directory is not None and not any(p.directory == directory for p in known):
            known.append(ownership.Place(name, root, directory))

    if refusal := hybrid_refusal(name, panes, lemons, known):
        return [], [], refusal

    candidates = {
        place.directory: place
        for pane in panes
        if pane.session == name and pane.path is not None
        for place in [ownership.place_at(pane.path, known)]
        if place is not None
    }
    candidates.update(
        {place.directory: place for place in known if session.sanitize_name(place.key) == name}
    )
    if not lemons and (
        len(candidates) != 1
        or any(
            pane.path is None
            or not pane.path.resolve().is_relative_to(next(iter(candidates)).resolve())
            for pane in panes
            if pane.session == name
        )
    ):
        return (
            [],
            [
                "No lemons identify a place and pane directories are not consistent; no directories will be released"
            ],
            "",
        )

    released: list[ownership.Place] = []
    kept: list[str] = []
    for place in sorted(candidates.values(), key=lambda p: (p.key, str(p.directory))):
        if reason := _kept_reason(place, name, panes, known):
            kept.append(f"directory {place.key!r} stays ({reason})")
        else:
            released.append(place)
    return released, kept, ""


def resolve(config: Config, name: str) -> tuple[TossTarget | None, str]:
    if config.places.is_protected_session(name):
        return None, (
            f"Session {name!r} is protected and will not be torn down. "
            "Change `protected_sessions` under [places] if that is wrong."
        )

    panes = ownership.pane_snapshot()
    if panes is None:
        return None, f"Could not inspect panes in session {name!r}; nothing was closed"

    windows: dict[str, list[ownership.Pane]] = {}
    for pane in panes:
        if pane.session == name:
            windows.setdefault(pane.window, []).append(pane)
    lemons = workspace_purpose.lemon_panes(name)
    if lemons is None:
        return None, f"Could not inspect lemons in workspace {name!r}; nothing was closed"
    lemons.intersection_update(pane.pane for pane in panes if pane.session == name)
    places, kept, refusal = _directories(config, name, panes, lemons)
    if refusal:
        return None, refusal
    return TossTarget(name, places, places[0] if places else None, windows, {}, [], tuple(kept)), ""
