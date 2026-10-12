"""Resolving a path written without its vault root, and the vault folders a regex can't cover."""

from collections import abc
from pathlib import Path


def spaced_folders(roots: abc.Iterable[Path], excluded: str = "") -> list[str]:
    """Names of folders directly under *roots* that contain a space.

    Hidden folders and names containing a character in *excluded* are left out.
    """
    return sorted(
        {
            entry.name
            for root in roots
            if root.expanduser().is_dir()
            for entry in root.expanduser().iterdir()
            if " " in entry.name
            and not entry.name.startswith(".")
            and not any(c in entry.name for c in excluded)
            and entry.is_dir()
        }
    )


def resolve(path: Path, roots: abc.Iterable[Path]) -> Path | None:
    """*path* expanded when it is absolute or `~`-rooted, else its file under the first root holding it.

    None when a relative path is under no root.
    """
    if path.is_absolute() or path.parts[:1] == ("~",):
        return path.expanduser()

    return next((found for root in roots if (found := root.expanduser() / path).is_file()), None)
