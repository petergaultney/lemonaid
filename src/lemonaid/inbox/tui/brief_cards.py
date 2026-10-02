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


def _waited(seconds: float) -> str:
    days = int(max(0, seconds) // 86400)
    if days:
        return f"{days} day" if days == 1 else f"{days} days"

    return brief_status.age(seconds).removesuffix(" ago").replace("just now", "<1m")


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
    area: str = ""  # the part of its project the brief says it works in
    mid_turn: bool = False
    since: float = 0.0  # when the brief entered its status; 0 when unrecorded

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

    def extra_lines(self, age_inline: bool) -> int:
        """Lines the brief adds to its card: the age, unless it is *age_inline* on the
        context line, and each of the three above it has.
        """
        return (
            (not age_inline)
            + bool(self.needs_line)
            + bool(self.waiting_line)
            + bool(self.running_line)
        )

    def age(self, now: float, stale_hours: float) -> str:
        """How long a waiting brief has waited, else the brief's age.

        The age follows the brief's own status when the card is drawn as another.
        """
        stale = (
            " (stale)"
            if self.shown in {"working", "running", "waiting"}
            and now - self.mtime >= stale_hours * 3600
            else ""
        )
        if self.shown == "waiting" and self.since:
            return f"waiting {_waited(now - self.since)}{stale}"

        held = f"{self.status} · " if self.shown != self.status else ""
        return f"{held}updated {brief_status.age(max(0, now - self.mtime))}{stale}"


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
        parts.area,
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
