"""Which places a tmux session occupies.

Derived from tmux at the moment it's asked, never recorded. A session owns the
managed directories its panes sit in. Nothing has to be written down when a place
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


class Pane(ty.NamedTuple):
    session: str
    window: str  # tmux's window ID, like '@12'; stable for the window's life
    pane: str  # tmux's pane ID, like '%7'
    path: Path | None  # None when tmux could not say where the pane is


def panes() -> list[Pane]:
    """Every live pane that is somebody's work.

    lemonaid's own scratch panes and follow-mode placeholders are left out: they
    sit beside a lemon rather than being work of their own, so nothing should be
    decided from where they are.
    """
    try:
        result = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{session_name}\t#{window_id}\t#{pane_id}\t#{pane_current_path}"
                "\t#{@lemonaid_scratch}\t#{pane_start_command}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.warning("could not list panes: %s", e)
        return []

    found = []
    for line in result.stdout.splitlines():
        session, window, pane, path, scratch, start_command = line.split("\t", 5)
        if scratch == "1" or "LEMONAID_PLACEHOLDER" in start_command:
            continue
        if session:
            found.append(Pane(session, window, pane, Path(path) if path else None))

    return found


def pane_paths() -> dict[str, list[Path]]:
    """Every live session's pane working directories, by session name."""
    by_session: dict[str, list[Path]] = {}
    for pane in panes():
        if pane.path is not None:
            by_session.setdefault(pane.session, []).append(pane.path)

    return by_session


def managed_places(config: Config) -> list[Place]:
    """Every place every configured root reports.

    Listed once per call rather than per directory: the `list` hook is a
    subprocess, and resolving a session's places means testing every pane path
    against every managed directory.
    """
    places: list[Place] = []
    for root in config.places.roots:
        for directory in hooks.list_directories(root):
            try:
                key = str(directory.relative_to(root.path))
            except ValueError:
                _log.warning(
                    "place root %s reported directory outside itself: %s",
                    root.path,
                    directory,
                )
                continue
            places.append(Place(key, root, directory))

    return places


def place_at(path: Path, places: abc.Iterable[Place]) -> Place | None:
    """The place *path* is in: the most specific one whose directory contains it.

    A pane's working directory says what the pane is for right now. Processes
    with a purpose of their own (an editor, a lemon) keep the directory they were
    started in, and a shell that wandered into a place is in that place for as
    long as it stays - so at or below the directory is the test, not exactly at
    it. Protected places count here; callers that must not act on one exclude it.
    """
    resolved = path.resolve()

    return max(
        (
            place
            for place in places
            if resolved == place.directory.resolve()
            or place.directory.resolve() in resolved.parents
        ),
        key=lambda place: len(place.directory.parts),
        default=None,
    )


def places_of(
    session: str, config: Config, places: abc.Sequence[Place] | None = None
) -> list[Place]:
    """The places *session* occupies: those its panes sit at or below.

    Protected places are excluded. They can never be released, so counting one
    as owned would list it in every teardown confirmation - and a line you learn
    to skip past is how a real one gets missed. Everyone passes through the
    trunk worktree; that is not what owning a place means.

    Pass *places* to avoid re-listing when resolving several sessions.
    """
    known = managed_places(config) if places is None else places

    found = {
        place.directory: place
        for place in (place_at(path, known) for path in pane_paths().get(session, []))
        if place is not None and not place.root.is_protected(place.key)
    }

    return sorted(found.values(), key=lambda place: place.key)


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
