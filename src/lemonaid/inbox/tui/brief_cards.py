"""Cached brief details used by inbox cards."""

import dataclasses
from pathlib import Path

from rich.style import Style

from ...brief import now as brief_now
from ...brief import status as brief_status
from .. import turns
from .utils import ATTENTION_COLOR

MERGE_COLOR = "#4fb35a"
ALERT_COLOR = "#c62828"
REVIEW_COLOR = "#8a5a2b"
RUNNING_COLOR = "#00838f"
# The running process named on a card, lighter than the headline fill so it reads on the plain background.
RUNNING_TEXT_COLOR = "#4fc3cc"
# Headline colours for the statuses that want a look: an alert lemon needs you
# urgently, a blocked one waits on you, a merge one waits only on your merge, a
# review one waits on a teammate's approving review, a running one is minding a
# long process, and a done one is ready to clean up.
STATUS_STYLES = {
    "alert": Style(color="#ffffff", bgcolor=ALERT_COLOR),
    "blocked": Style(color="#000000", bgcolor=ATTENTION_COLOR),
    "merge": Style(color="#000000", bgcolor=MERGE_COLOR),
    "review": Style(color="#ffffff", bgcolor=REVIEW_COLOR),
    "running": Style(color="#ffffff", bgcolor=RUNNING_COLOR),
    "done": Style(color="#ffffff", bgcolor="#285995"),
}
# The unread dot on a filled headline or row, where the yellow one would vanish.
DOT_STYLES = {
    "alert": "bold #ffffff",
    "blocked": "bold #000000",
    "merge": "bold #000000",
    "review": "bold #ffffff",
    "running": "bold #ffffff",
}


@dataclasses.dataclass(frozen=True)
class CardBrief:
    """A brief as its card needs it.

    `status` is the brief's own, which places the card in the list; `shown` is
    the one the card is drawn as, which differs while the lemon is mid-turn.
    """

    status: str
    waiting_on: str
    mtime: float
    needs: str = ""
    needs_label: str = "Needs"
    running: str = ""
    mid_turn: bool = False

    @property
    def shown(self) -> str:
        return turns.shown(self.status) if self.mid_turn else self.status

    @property
    def needs_line(self) -> str:
        """What a person has to do, under the label the worker wrote; "" once done or mid-turn."""
        return (
            f"{self.needs_label}: {self.needs}"
            if self.needs and self.shown == self.status and self.status != "done"
            else ""
        )

    @property
    def waiting_line(self) -> str:
        return self.waiting_on if self.shown == "waiting" else ""

    @property
    def running_line(self) -> str:
        return self.running if self.shown == "running" else ""

    @property
    def extra_lines(self) -> int:
        """Lines the brief adds to its card: the age, and each of the three above it has."""
        return 1 + bool(self.needs_line) + bool(self.waiting_line) + bool(self.running_line)

    def age(self, now: float, stale_hours: float) -> str:
        """The brief's age, after its own status when the card is drawn as another."""
        elapsed = max(0, now - self.mtime)
        age = brief_status.age(elapsed)
        held = f"{self.status} · " if self.shown != self.status else ""
        if (
            self.shown in {"working", "running", "waiting"}
            and now - self.mtime >= stale_hours * 3600
        ):
            return f"{held}updated {age} (stale)"

        return f"{held}updated {age}"


def mid_turn(card: CardBrief) -> CardBrief:
    return dataclasses.replace(card, mid_turn=True)


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
        brief_now.summary(now.running),
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
