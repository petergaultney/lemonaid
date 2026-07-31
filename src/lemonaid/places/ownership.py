"""Which places a tmux session occupies.

Derived from tmux at the moment it's asked, never recorded. A session's panes
have working directories; the managed ones among those are what that session
owns. Nothing has to be written down when a place is opened, which means nothing
can drift - a directory acquired by hand, by `place open`, or by an agent all
look the same afterward.

tmux keeps reporting a pane's original path after that directory is deleted, so
a session whose place is already gone still resolves rather than becoming
untossable.
"""

import subprocess
import typing as ty
from collections import abc
from pathlib import Path

from ..config import Config, PlaceRoot
from ..log import get_logger
from . import hooks

_log = get_logger("places.ownership")

_TIMEOUT_SECONDS = 5


class Place(ty.NamedTuple):
    key: str
    root: PlaceRoot
    directory: Path

    @property
    def exists(self) -> bool:
        return self.directory.is_dir()


def pane_paths() -> dict[str, list[Path]]:
    """Every live session's pane working directories, by session name."""
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{session_name}\t#{pane_current_path}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("could not list panes: %s", e)
        return {}

    by_session: dict[str, list[Path]] = {}
    for line in result.stdout.splitlines():
        session, _, path = line.partition("\t")
        if session and path:
            by_session.setdefault(session, []).append(Path(path))

    return by_session


def managed_places(config: Config) -> list[Place]:
    """Every place every configured root reports.

    Listed once per call rather than per directory: the `list` hook is a
    subprocess, and resolving a session's places means testing every pane path
    against every managed directory.
    """
    return [
        Place(str(directory.relative_to(root.path)), root, directory)
        for root in config.places.roots
        for directory in hooks.list_directories(root)
    ]


def _place_containing(places: abc.Sequence[Place], path: Path) -> Place | None:
    """The innermost place *path* sits in, or None.

    A pane deep inside a place still counts as being in that place. Innermost
    wins so a place nested inside another resolves to the one you're actually in.
    """
    return max(
        (place for place in places if path == place.directory or place.directory in path.parents),
        key=lambda place: len(place.directory.parts),
        default=None,
    )


def places_of(
    session: str, config: Config, places: abc.Sequence[Place] | None = None
) -> list[Place]:
    """The places *session* occupies, innermost per pane, deduplicated.

    Protected places are excluded. They can never be released, so counting one
    as owned would list it in every teardown confirmation - and a line you learn
    to skip past is how a real one gets missed. Everyone passes through the
    trunk worktree; that is not what owning a place means.

    Pass *places* to avoid re-listing when resolving several sessions.
    """
    known = managed_places(config) if places is None else places
    paths = pane_paths().get(session, [])

    found = {
        place.directory: place
        for place in (_place_containing(known, path) for path in paths)
        if place is not None and not place.root.is_protected(place.key)
    }

    return sorted(found.values(), key=lambda place: place.key)


def session_holding(directory: Path) -> str:
    """The session with a pane in *directory* (or below it), if any.

    Used to go from a named key back to the session that owns it. Prefers an
    exact match, since a session sitting in a subdirectory of another place's
    directory is the weaker claim.
    """
    resolved = directory.resolve()
    candidates = [
        (session, path)
        for session, paths in pane_paths().items()
        for path in paths
        if path == resolved or resolved in path.parents or resolved == path
    ]

    exact = next((session for session, path in candidates if path == resolved), "")

    return exact or next((session for session, _ in candidates), "")


def find_place(config: Config, key: str) -> Place | None:
    """The place *key* names, searched across every root.

    A key is resolved by asking each root's `path_of` hook, so this works for a
    place whose directory is listed and for one that only the hook knows about.
    """
    return next(
        (
            Place(key, root, directory)
            for root in config.places.roots
            for directory in [hooks.directory_for_key(root, key)]
            if directory is not None
        ),
        None,
    )
