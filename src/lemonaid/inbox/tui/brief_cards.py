"""Cached brief details used by inbox cards."""

import dataclasses
import threading
from pathlib import Path

from rich.style import Style
from rich.text import Text

from ...brief import now as brief_now
from ...brief import status as brief_status
from .. import turns
from . import utils
from .utils import ATTENTION_COLOR

MERGE_COLOR = "#4fb35a"
ALERT_COLOR = "#c62828"
REVIEW_COLOR = "#8a5a2b"
APPROVE_COLOR = "#7e57c2"
RUNNING_COLOR = "#00838f"
# The running process named on a card, lighter than the headline fill so it reads on the plain background.
RUNNING_TEXT_COLOR = "#4fc3cc"
RUNNING_TEXT_COLOR_LIGHT = "#00707a"

_STATE_STYLES = {
    "alert": "bold #ff5c5c",
    "blocked": f"bold {ATTENTION_COLOR}",
    "merge": f"bold {MERGE_COLOR}",
    "approve": "bold #b39ddb",
    "review": "bold #c08a52",
    "running": f"bold {RUNNING_TEXT_COLOR}",
    "done": "bold #6f9fe0",
    "working": "bold",
    "waiting": "bright_black",
}
_STATE_STYLES_LIGHT = {
    **_STATE_STYLES,
    "alert": f"bold {ALERT_COLOR}",
    "blocked": f"bold {utils.ATTENTION_TEXT_LIGHT}",
    "merge": "bold #2e7d32",
    "approve": "bold #5e35b1",
    "review": f"bold {REVIEW_COLOR}",
    "running": f"bold {RUNNING_TEXT_COLOR_LIGHT}",
    "done": "bold #285995",
}


def status_text_style(state: str, default: str = "") -> str:
    """The foreground colour for a status word on the card's plain background."""
    styles = _STATE_STYLES_LIGHT if utils.light_theme() else _STATE_STYLES
    return styles.get(state, default)


def running_text() -> str:
    """The running process's colour as text, for the theme the app is drawing."""
    return RUNNING_TEXT_COLOR_LIGHT if utils.light_theme() else RUNNING_TEXT_COLOR


# Headline colours for the statuses that want a look: an alert lemon needs you
# urgently, a blocked one waits on you, a merge one waits only on your merge, an
# approve one waits only on your approval of a teammate's PR, a review one waits
# on a teammate's approving review, a running one is minding a long process, and
# a done one is ready to clean up.
STATUS_STYLES = {
    "alert": Style(color="#ffffff", bgcolor=ALERT_COLOR),
    "blocked": Style(color="#000000", bgcolor=ATTENTION_COLOR),
    "merge": Style(color="#000000", bgcolor=MERGE_COLOR),
    "approve": Style(color="#ffffff", bgcolor=APPROVE_COLOR),
    "review": Style(color="#ffffff", bgcolor=REVIEW_COLOR),
    "running": Style(color="#ffffff", bgcolor=RUNNING_COLOR),
    "done": Style(color="#ffffff", bgcolor="#285995"),
}
# The unread dot on a filled headline or row, where the yellow one would vanish.
DOT_STYLES = {
    "alert": "bold #ffffff",
    "blocked": "bold #000000",
    "merge": "bold #000000",
    "approve": "bold #ffffff",
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

    def age_text(self, now: float, stale_hours: float, *, style: str = "") -> Text:
        """The age label with a held status styled independently from its age."""
        value = self.age(now, stale_hours)
        held = f"{self.status} · " if self.shown != self.status else ""
        text = Text(value, style=style)
        if held:
            text.stylize(status_text_style(self.status, "dim"), 0, len(held))
        return text


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
        self._lock = threading.RLock()

    def get(self, path: Path) -> CardBrief | None:
        with self._lock:
            return self._get(path)

    def _get(self, path: Path) -> CardBrief | None:
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
