"""Who wrote last in each thread of a review doc."""

from pathlib import Path

from ..doc_plugins import configured, document
from ..plugins.command import Plugins


def read(path: Path, plugins: Plugins | None = None) -> frozenset[str]:
    """*plugins* default to the configured ones."""
    try:
        text = path.read_text()
    except (OSError, UnicodeError):
        return frozenset()

    return document.last_authors(configured.plugins() if plugins is None else plugins, path, text)


class Cache:
    """`read`, done again only when a doc's size or mtime changes; the inbox asks every refresh.

    Used by the UI thread and the inbox's refresh worker; each change is one dict operation.
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
