"""Which place a child lemon works in, from its cwd and its tmux session's panes."""

import dataclasses
from collections import abc
from pathlib import Path

from ..config import PlaceRoot
from ..places import ownership


@dataclasses.dataclass(frozen=True)
class World:
    sessions: abc.Set[str] | None  # live tmux sessions; None when tmux couldn't say
    clients: abc.Mapping[str, int] | None  # attached clients per session; None likewise
    places: abc.Sequence[ownership.Place]  # every managed place, protected ones included
    panes: abc.Mapping[str, abc.Sequence[Path]]  # pane directories per live session
    roots: abc.Sequence[PlaceRoot]


@dataclasses.dataclass(frozen=True)
class Place:
    key: str
    dir: str
    exists: bool
    listed: bool  # whether its root's `list` hook reports it, rather than inferred from paths


def _unlisted(paths: abc.Iterable[Path], roots: abc.Sequence[PlaceRoot]) -> Place | None:
    """The shallowest of *paths* below a root, as a place keyed by its path from the root.

    For a root with no `list` hook. A session's panes sit at its place's own
    directory, while its lemon may have wandered below it, so the shallowest wins.
    """
    found = [
        (path, root, str(path.relative_to(root.path.resolve())))
        for path in paths
        for root in roots
        if path.is_relative_to(root.path.resolve()) and path != root.path.resolve()
    ]
    kept = [(path, key) for path, root, key in found if not root.is_protected(key)]
    if not kept:
        return None

    path, key = min(kept, key=lambda pair: len(pair[0].parts))
    return Place(key, str(path), path.is_dir(), listed=False)


def of(cwd: str, session: str, world: World) -> Place | None:
    """The innermost unprotected place holding the lemon's *cwd*, else one its session sits at.

    A lemon that hasn't started has no cwd yet, but `place open` left its
    session's panes at the place.
    """
    unprotected = [p for p in world.places if not p.root.is_protected(p.key)]
    path = Path(cwd).resolve() if cwd else None
    holding = [p for p in unprotected if path and path.is_relative_to(p.directory.resolve())]
    panes = [p.resolve() for p in world.panes.get(session, ())] if session else []
    best = (
        max(holding, key=lambda p: len(p.directory.parts))
        if holding
        else next((p for p in unprotected if p.directory.resolve() in panes), None)
    )
    if best:
        return Place(best.key, str(best.directory), best.exists, listed=True)

    listed_roots = {p.root.path for p in world.places}
    return _unlisted(
        [*panes, *([path] if path else [])],
        [r for r in world.roots if r.path not in listed_roots],
    )
