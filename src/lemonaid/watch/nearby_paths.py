"""Bounded identity-based suggestions; callers must confirm a candidate themselves."""

import os
import pathlib
import stat
from collections import deque

from ..log import get_logger

Identity = tuple[int, int, int, float]
_log = get_logger("watch.nearby")


def identity(path: pathlib.Path) -> Identity:
    info = path.stat(follow_symlinks=False)
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), getattr(info, "st_birthtime", 0.0)


def candidates(
    path: pathlib.Path,
    previous: Identity,
    *,
    entries: int = 1024,
    directories: int = 32,
) -> list[pathlib.Path]:
    visited: set[pathlib.Path] = set()
    found: list[pathlib.Path] = []
    for root in (path.parent, path.parent.parent):
        queue = deque([(root, 0)])
        while queue and directories > 0 and entries > 0:
            parent, depth = queue.popleft()
            if parent in visited:
                continue

            visited.add(parent)
            directories -= 1
            try:
                with os.scandir(parent) as listing:
                    for entry in listing:
                        if entries <= 0:
                            return found

                        entries -= 1
                        if entry.is_symlink():
                            continue

                        candidate = pathlib.Path(entry.path)
                        if entry.inode() == previous[1] and identity(candidate) == previous:
                            found.append(candidate)
                            if len(found) == 3:
                                return found

                        if (
                            depth < 1
                            and not entry.name.startswith(".")
                            and entry.is_dir(follow_symlinks=False)
                        ):
                            queue.append((candidate, depth + 1))
            except FileNotFoundError:
                continue

            except OSError as error:
                _log.warning("Cannot search %s for a missing watch target: %s", parent, error)
    return found
