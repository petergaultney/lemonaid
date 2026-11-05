"""Where a moved lemon goes: a directory, and the terminal workspace it joins there.

A key names a place under a root and is acquired through the root's hooks; a
spelling that starts like a path names an existing directory as is. A front end
without its own way to pick a workspace gets one named for the key or directory.
"""

import dataclasses
import typing as ty
from collections import abc
from pathlib import Path

from ...config import Config, PlaceRoot
from ...front_end import location, pick
from ...places import hooks, lifecycle


@dataclasses.dataclass(frozen=True)
class Destination:
    directory: str
    key: str  # "" for a directory given as a path
    front_end: str
    workspace: str  # tmux session or WezTerm workspace; cmux ignores it


def is_path(spelling: str) -> bool:
    return spelling.startswith(("/", "~", "."))


def _directory(spelling: str, root: PlaceRoot | None, acquire: bool) -> Path:
    if is_path(spelling):
        directory = Path(spelling).expanduser().resolve()
        if not directory.is_dir():
            raise ValueError(f"{directory} is not a directory")

        return directory

    if root is None:
        raise ValueError(
            f"No places root with a key vocabulary covers the lemon's directory, so {spelling!r} "
            "names nothing. Pass --root, or a directory path starting with / ~ or ."
        )

    if not acquire:
        found = hooks.directory_for_key(root, spelling)
        if found is None:
            raise ValueError(
                f"{spelling!r} does not exist under {root.path} yet; a move without --dry-run "
                "acquires it through the root's hooks"
            )

        return found.resolve()

    found, error = lifecycle.acquire_key(spelling, root)
    if found is None:
        raise ValueError(error or f"Could not acquire {spelling!r}")

    return found.resolve()


def resolve(
    spelling: str,
    root: PlaceRoot | None,
    metadata: abc.Mapping[str, ty.Any],
    switch_source: str,
    config: Config,
    acquire: bool,
) -> Destination:
    """Where *spelling* puts a lemon recorded with *metadata*; *acquire* creates a missing key."""
    directory = _directory(spelling, root, acquire)
    key = "" if is_path(spelling) else spelling
    where = location.of(metadata, switch_source)
    found = pick.named(where.front_end)
    workspace = (
        found.relocation.workspace(where.instance, directory, key, config)
        if found and found.relocation
        else key or directory.name
    )
    return Destination(str(directory), key, where.front_end, workspace)
