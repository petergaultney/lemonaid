"""Process-lifetime project names, resolved serially outside the UI thread."""

import asyncio
from collections import abc, deque

from ...config import PlaceRoot
from ...log import get_logger
from ...places import hooks

_log = get_logger("inbox.project_names")


def resolve(root: PlaceRoot, directory: str) -> str:
    try:
        lines = hooks.run_lines(root, root.project_name, directory=directory, timeout=5)
    except UnicodeError as error:
        _log.warning("could not decode project_name output in %s: %s", root.path, error)
        return ""
    if len(lines) > 1:
        _log.warning("project_name hook in %s returned more than one name", root.path)
        return ""

    return lines[0] if lines else ""


class Cache:
    def __init__(self) -> None:
        self.names: dict[str, str] = {}
        self._pending: deque[tuple[str, PlaceRoot]] = deque()
        self._running = False

    def request(self, directory: str, root: PlaceRoot | None) -> bool:
        """Reserve a directory once; True asks the caller to start the drain worker."""
        if not directory or directory in self.names or root is None or not root.project_name:
            return False

        self.names[directory] = ""
        self._pending.append((directory, root))
        if self._running:
            return False

        self._running = True
        return True

    async def drain(self, changed: abc.Callable[[], None]) -> None:
        try:
            while self._pending:
                directory, root = self._pending.popleft()
                self.names[directory] = await asyncio.to_thread(resolve, root, directory)
                if self.names[directory]:
                    changed()
        finally:
            self._running = False
