"""Which places a tmux session occupies.

Derived from tmux at the moment it's asked, never recorded. A session owns the
managed directories its panes sit at. Nothing has to be written down when a place
is opened, which means nothing can drift - a directory acquired by hand, by
`place open`, or by an agent all look the same afterward.

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


def places_of(
    session: str, config: Config, places: abc.Sequence[Place] | None = None
) -> list[Place]:
    """The places *session* occupies: panes sitting at a place's own directory.

    A pane must be *at* the directory, not below it. Working in a place and
    having wandered into one are indistinguishable by path, and only one of them
    should put a worktree on a teardown list - so a pane deep inside a tree
    doesn't claim it. Sessions keep a pane at the root in practice, which is why
    this loses nothing: a session working in a place has such a pane, while one
    that merely visited another's worktree does not.

    Protected places are excluded. They can never be released, so counting one
    as owned would list it in every teardown confirmation - and a line you learn
    to skip past is how a real one gets missed. Everyone passes through the
    trunk worktree; that is not what owning a place means.

    Pass *places* to avoid re-listing when resolving several sessions.
    """
    known = managed_places(config) if places is None else places
    at_directory = {place.directory: place for place in known}

    found = {
        place.directory: place
        for place in (at_directory.get(path) for path in pane_paths().get(session, []))
        if place is not None and not place.root.is_protected(place.key)
    }

    return sorted(found.values(), key=lambda place: place.key)


def sessions_holding(directory: Path) -> list[str]:
    """Every session with a pane at *directory*.

    The reverse of `places_of`, and exact for the same reason: a session that
    wandered into this directory is not the one to tear down when it is named.

    More than one is normal - a second session can have a window open at a place
    another one is working in - so this reports all of them rather than picking.
    Choosing arbitrarily would mean a named key sometimes tears down a session
    that has nothing to do with it.
    """
    resolved = directory.resolve()

    return sorted(
        {session for session, paths in pane_paths().items() for path in paths if path == resolved}
    )


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
