"""Cached brief details used by inbox cards."""

import dataclasses
import re
from pathlib import Path

from ...brief import status as brief_status

_WAITING = re.compile(r"\s*-\s*Waiting on:\s*(.*)", re.IGNORECASE)


@dataclasses.dataclass(frozen=True)
class CardBrief:
    status: str
    waiting_on: str
    mtime: float

    def age(self, now: float, stale_hours: float) -> str:
        elapsed = max(0, now - self.mtime)
        age = brief_status.age(elapsed)
        if self.status in {"working", "waiting"} and now - self.mtime >= stale_hours * 3600:
            return f"updated {age} (stale)"

        return f"updated {age}"


def _parse(text: str, mtime: float) -> CardBrief | None:
    parts = brief_status.split(text)
    if not parts.status:
        return None

    waiting_on = next(
        (match[1].strip() for line in parts.now.splitlines() if (match := _WAITING.fullmatch(line))),
        "",
    )
    return CardBrief(parts.status, "" if waiting_on.lower() == "nothing" else waiting_on, mtime)


class BriefCache:
    def __init__(self) -> None:
        self._entries: dict[Path, tuple[int, int, CardBrief | None]] = {}

    def get(self, path: Path) -> CardBrief | None:
        try:
            stat = path.stat()
        except OSError:
            self._entries.pop(path, None)
            return None

        cached = self._entries.get(path)
        if cached and cached[:2] == (stat.st_mtime_ns, stat.st_size):
            return cached[2]

        try:
            brief = _parse(path.read_text(), stat.st_mtime)
        except OSError:
            self._entries.pop(path, None)
            return None

        self._entries[path] = (stat.st_mtime_ns, stat.st_size, brief)
        return brief
