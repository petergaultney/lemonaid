"""Who wrote last in each thread of a review doc."""

from pathlib import Path

from ..watch import relay_comments


def read(path: Path) -> frozenset[str]:
    try:
        return frozenset(relay_comments.last_authors(path.read_text()))
    except (OSError, UnicodeError):
        return frozenset()


class Cache:
    """`read`, done again only when a doc's size or mtime changes; the inbox asks every refresh.

    Mutated only on the UI thread.
    """

    def __init__(self) -> None:
        self._entries: dict[Path, tuple[int, int, frozenset[str]]] = {}

    def read(self, path: Path) -> frozenset[str]:
        try:
            stat = path.stat()
        except OSError:
            self._entries.pop(path, None)
            return frozenset()

        cached = self._entries.get(path)
        if cached and cached[:2] == (stat.st_mtime_ns, stat.st_size):
            return cached[2]

        found = read(path)
        self._entries[path] = (stat.st_mtime_ns, stat.st_size, found)
        return found
