"""Cached brief details used by inbox cards."""

import dataclasses
from pathlib import Path

from ...brief import now as brief_now
from ...brief import status as brief_status


@dataclasses.dataclass(frozen=True)
class CardBrief:
    status: str
    waiting_on: str
    mtime: float
    needs: str = ""

    @property
    def subtitle(self) -> str:
        """What a person has to do, else what a waiting lemon is waiting on."""
        if self.needs and self.status != "done":
            return self.needs

        return self.waiting_on if self.status == "waiting" else ""

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

    now = brief_now.parse(parts.now)
    return CardBrief(
        parts.status,
        brief_now.summary(now.waiting_on),
        mtime,
        brief_now.summary(now.needs),
    )


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
