"""Cached brief details used by inbox cards."""

import dataclasses
from pathlib import Path

from rich.style import Style

from ...brief import now as brief_now
from ...brief import status as brief_status
from .utils import ATTENTION_COLOR

MERGE_COLOR = "#4fb35a"
ALERT_COLOR = "#c62828"
# Headline colours for the statuses that want a look: an alert lemon needs you
# urgently, a blocked one waits on you, a merge one waits only on your merge,
# and a done one is ready to clean up.
STATUS_STYLES = {
    "alert": Style(color="#ffffff", bgcolor=ALERT_COLOR),
    "blocked": Style(color="#000000", bgcolor=ATTENTION_COLOR),
    "merge": Style(color="#000000", bgcolor=MERGE_COLOR),
    "done": Style(color="#ffffff", bgcolor="#285995"),
}
# The unread dot on a filled headline or row, where the yellow one would vanish.
DOT_STYLES = {"alert": "bold #ffffff", "blocked": "bold #000000", "merge": "bold #000000"}


@dataclasses.dataclass(frozen=True)
class CardBrief:
    status: str
    waiting_on: str
    mtime: float
    needs: str = ""
    needs_label: str = "Needs"

    @property
    def needs_line(self) -> str:
        """What a person has to do, under the label the worker wrote; "" once done."""
        return f"{self.needs_label}: {self.needs}" if self.needs and self.status != "done" else ""

    @property
    def waiting_line(self) -> str:
        return self.waiting_on if self.status == "waiting" else ""

    @property
    def extra_lines(self) -> int:
        """Lines the brief adds to its card: the age, and each of the two above it has."""
        return 1 + bool(self.needs_line) + bool(self.waiting_line)

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
        now.needs_label,
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
