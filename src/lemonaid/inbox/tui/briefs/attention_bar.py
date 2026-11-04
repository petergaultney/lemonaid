"""The brief view's top line: the inbox's attention summary, its badges in the inbox's
slots. For `status_pulse_seconds` after a lemon's brief enters a status, that status's
badge pulses.

It is fed the inbox's own frames, so it adds no read of its own.
"""

import math
import time
import typing as ty
from collections import abc

from textual import events
from textual.timer import Timer
from textual.widgets import Static

from .... import config, status_registry
from ... import db, view
from ..live import attention_summary

_PERIOD = 2.0  # seconds a badge takes to brighten and fade back
_TICK = 1 / 15  # seconds between a pulsing line's frames

# The line's form for a width, rows and their statuses: cards or not, slot starts, slot width.
Layout = abc.Callable[
    [int, abc.Sequence[db.Notification], abc.Mapping[str, str]],
    tuple[bool, abc.Mapping[str, int], int],
]


def _entered(before: abc.Mapping[str, str], after: abc.Mapping[str, str]) -> set[str]:
    """The set statuses a lemon in both changed to."""
    return {
        status
        for channel, status in after.items()
        if status and channel in before and before[channel] != status
    }


def _pulses(
    current: abc.Mapping[str, float],
    before: abc.Mapping[str, str],
    after: abc.Mapping[str, str],
    now: float,
    seconds: float,
) -> dict[str, float]:
    """When each status's pulse began: *current*'s still running, and a new one for each
    status a lemon entered between *before* and *after*."""
    return {
        **{status: began for status, began in current.items() if now - began < seconds},
        **{status: now for status in _entered(before, after)},
    }


def _glow(began: float, now: float) -> float:
    """How lit a badge is, from 0 to 1, easing in and out from when its pulse *began*."""
    return (1 - math.cos(2 * math.pi * (now - began) / _PERIOD)) / 2


class AttentionBar(Static):
    DEFAULT_CSS = """
    AttentionBar {
        height: 1;
        padding: 0;
    }
    """

    def __init__(
        self,
        pulse_seconds: float,
        layout: Layout,
        clock: abc.Callable[[], float] = time.monotonic,
        **kwargs: ty.Any,
    ) -> None:
        """*layout* is asked again on every draw, so the badges follow the pane's size."""
        super().__init__("", **kwargs)
        self._pulse_seconds = pulse_seconds
        self._layout = layout
        self._clock = clock
        self._statuses: dict[str, str] | None = None  # each lemon's own brief status, last seen
        self._pulses: dict[str, float] = {}  # when each pulsing status's pulse began
        self._rows: list[db.Notification] = []
        self._counted: dict[str, str] = {}  # the status each row is counted under
        self._ticking: Timer | None = None

    def observe(self, active: "view.Active") -> None:
        """Count *active*'s lemons by status, and pulse any status a lemon's brief entered."""
        after = {
            n.channel: card.status if (card := active.cards.get(n.channel)) else ""
            for n in active.rows
        }
        if self._statuses is not None and self._pulse_seconds > 0:
            self._pulses = _pulses(
                self._pulses, self._statuses, after, self._clock(), self._pulse_seconds
            )
        self._statuses = after
        self._rows = list(active.rows)
        self._counted = view.statuses(active.cards, active.rows)
        if self._pulses and self._ticking is None:
            self._ticking = self.set_interval(_TICK, self._draw)
        self._draw()

    def on_resize(self, event: events.Resize) -> None:
        self._draw()

    def _draw(self) -> None:
        now = self._clock()
        self._pulses = {
            status: began
            for status, began in self._pulses.items()
            if now - began < self._pulse_seconds
        }
        if not self._pulses and self._ticking is not None:
            self._ticking.stop()
            self._ticking = None
        cards, starts, slot = self._layout(self.size.width, self._rows, self._counted)
        self.update(
            attention_summary.line(
                self._rows,
                self._counted,
                status_registry.attention(config.brief_statuses()),
                cards,
                "",
                False,
                starts,
                slot,
                {status: _glow(began, now) for status, began in self._pulses.items()},
            )
        )
