"""Cached brief details used by inbox cards."""

import dataclasses
import threading
from pathlib import Path

from rich.style import Style
from rich.text import Text

from .... import config, status_registry
from ....brief import colors, hidden
from ....brief import now as brief_now
from ....brief import status as brief_status
from ....brief.colors import RUNNING_TEXT_COLOR, RUNNING_TEXT_COLOR_LIGHT
from ... import turns
from .. import utils


def status_text_style(state: str, default: str = "") -> str:
    return colors.status_text_style(state, default, light=utils.light_theme())


def needs_style(state: str) -> str:
    return status_text_style(state, utils.unread_marker_style())


def running_text() -> str:
    """The running process's colour as text, for the theme the app is drawing."""
    return RUNNING_TEXT_COLOR_LIGHT if utils.light_theme() else RUNNING_TEXT_COLOR


def status_style(status: str) -> Style | None:
    """A status's headline fill, from the configured statuses; None for no status."""
    found = status_registry.by_name(config.brief_statuses()).get(status)
    return Style(color=found.on_fill, bgcolor=found.fill) if found else None


def dot_style(status: str) -> str:
    """The unread dot on a filled headline or row, where the yellow one would vanish; ""
    when *status* fills nothing, or is done."""
    found = status_registry.by_name(config.brief_statuses()).get(status)
    return f"bold {found.on_fill}" if found and found.name != status_registry.DONE else ""


def _waited(seconds: float) -> str:
    days = int(max(0, seconds) // 86400)
    if days:
        return f"{days} day" if days == 1 else f"{days} days"

    return brief_status.age(max(0, seconds)).removesuffix(" ago")


@dataclasses.dataclass(frozen=True)
class CardBrief:
    """A brief as its card needs it.

    `status` is the brief's own, "" when it sets none; `placed` puts the card in
    the list and the fold, so a set status keeps its place through a turn; `shown` is the one the card is drawn as.
    """

    status: str
    waiting_on: str
    mtime: float
    needs: str = ""
    needs_label: str = "Needs"
    running: str = ""
    area: str = ""  # the part of its project the brief says it works in
    mid_turn: bool = False
    held_mid_turn: bool = False  # `mid_turn_working`: a set status is drawn `active` mid-turn
    mark: str = ""  # `deaf` or `dead`, from `presence`
    since: float = 0.0  # when it entered its status, or without one, its lemon's last report
    stuck: str = ""  # "stuck 45m: reviewer's move on #238", from the stall check
    asking: bool = (
        False  # its lemon is stuck on a permission prompt: `blocked`, whatever the brief says
    )
    hidden: bool = False  # `Hidden: yes`: left out of the default inbox
    contested: str = ""  # an open challenge to its Status, from `tasks.briefs.contested`

    @property
    def placed(self) -> str:
        if self.asking:
            return "blocked"

        if self.status:
            return self.status

        if self.mark == "dead":
            return self.mark  # a harness killed mid-turn leaves its turn open for a while

        return "active" if self.mid_turn else self.mark or "idle"

    @property
    def shown(self) -> str:
        if not self.status or self.asking:
            return self.placed

        return turns.shown(self.status) if self.mid_turn and self.held_mid_turn else self.status

    @property
    def held(self) -> bool:
        """Whether the card is drawn as other than the status its brief sets."""
        return bool(self.status) and self.shown != self.status

    @property
    def needs_line(self) -> str:
        """What a person has to do, under the label the worker wrote; "" once done or held."""
        return (
            f"{self.needs_label}: {self.needs}"
            if self.needs and not self.held and self.status != "done"
            else ""
        )

    @property
    def waiting_line(self) -> str:
        return self.waiting_on if not self.status and not self.mid_turn else ""

    @property
    def running_line(self) -> str:
        return self.running if self.shown == "running" else ""

    @property
    def contested_line(self) -> str:
        """The challenge to the brief's own Status; "" while the card shows another."""
        return f"contested: {self.contested}" if self.contested and not self.held else ""

    @property
    def stuck_line(self) -> str:
        return self.stuck if self.status != "done" else ""

    def extra_lines(self, age_inline: bool) -> int:
        """Lines the brief adds to its card: the age, unless it is *age_inline* on the
        context line, and each of the three above it has.
        """
        return (
            (not age_inline)
            + bool(self.needs_line)
            + bool(self.waiting_line)
            + bool(self.running_line)
            + bool(self.stuck_line)
            + bool(self.contested_line)
        )

    def _word(self) -> str:
        """The status the age line names: the brief's own when it sets one, else the lemon's."""
        return self.status or ("idle" if self.mark else self.shown)

    def _when(self, now: float) -> str:
        if not self.status:
            # mid-turn is happening now; otherwise, how long it has been idle
            return "just now" if self.shown == "active" else _waited(now - self.since)

        return brief_status.age(max(0.0, now - (self.since or self.mtime)))

    def _words(self) -> list[str]:
        """The status words the age line opens with: a `deaf` or `dead` mark, then the status."""
        return [word for word in (self.mark, self._word()) if word]

    def age(self, now: float) -> str:
        """The status and how long it has held it: `idle 1h`, `done 1m ago`, `dead · idle 3h`."""
        return f"{' · '.join(self._words())} {self._when(now)}"

    def age_text(self, now: float, *, style: str = "") -> Text:
        """The age label, with each status word in its own colour."""
        text = Text(self.age(now), style=style)
        start = 0
        for word in self._words():
            if word == self.mark or word == self.status:
                text.stylize(status_text_style(word, "dim"), start, start + len(word))
            if word == self.status and self.contested:
                text.stylize("strike", start, start + len(word))
            start += len(word) + len(" · ")
        return text


def _parse(text: str, mtime: float) -> CardBrief:
    parts = brief_status.split(text)
    now = brief_now.parse(parts.now)
    return CardBrief(
        parts.status,
        brief_now.summary(now.waiting_on),
        mtime,
        brief_now.summary(now.needs),
        now.needs_label,
        brief_now.summary(now.running),
        parts.area,
        hidden=hidden.is_hidden(text),
    )


class BriefCache:
    def __init__(self) -> None:
        self._entries: dict[Path, tuple[int, int, CardBrief]] = {}
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
