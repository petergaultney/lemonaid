"""The brief view's top line: the attention summary, its badge pulsing when a lemon enters it."""

import asyncio

import pytest
from textual.app import App, ComposeResult

from lemonaid.inbox import db, view
from lemonaid.inbox.tui.briefs import attention_bar
from lemonaid.inbox.tui.briefs.attention_bar import AttentionBar
from lemonaid.inbox.tui.live import group_headers
from lemonaid.inbox.tui.rows import brief_cards


def _active(statuses: dict[str, str]) -> view.Active:
    with db.connect() as conn:
        conn.execute("DELETE FROM notifications")
        rows = [db.add(conn, f"claude:{name}", "working", name, {}) for name in statuses]
    return view.Active(
        rows,
        {f"claude:{name}": brief_cards.CardBrief(s, "", 0.0) for name, s in statuses.items()},
        {},
        frozenset(),
    )


def test_only_a_set_status_a_lemon_moved_into_pulses():
    before = {"a": "review", "b": "", "c": "merge", "d": "blocked"}
    after = {"a": "merge", "b": "blocked", "c": "merge", "d": "", "new": "alert"}

    assert attention_bar._entered(before, after) == {"merge", "blocked"}


def test_pulses_expire_and_a_new_entry_restarts_its_status():
    pulses = attention_bar._pulses(
        {"merge": 0.0, "done": 8.0}, {"c": "review"}, {"c": "merge"}, 10.0, 10.0
    )

    assert pulses == {"done": 8.0, "merge": 10.0}


def test_a_pulse_starts_unlit_and_peaks_halfway():
    assert attention_bar._glow(5.0, 5.0) == pytest.approx(0.0)
    assert attention_bar._glow(5.0, 5.0 + attention_bar._PERIOD / 2) == pytest.approx(1.0)


def _slotted(width, rows, statuses):
    return True, group_headers.slot_starts(width, [], 0, 0, 4), 4


class _Bar(App[None]):
    def __init__(self, clock: list[float]) -> None:
        super().__init__()
        self._clock = clock

    def compose(self) -> ComposeResult:
        yield AttentionBar(10.0, _slotted, lambda: self._clock[0])


def _merge_badge_fill(bar: AttentionBar) -> str:
    rendered = bar.render()
    start = str(rendered).index(group_headers.badge("merge", 1).plain)
    return next(
        str(span.style.background)
        for span in rendered.spans
        if span.start <= start < span.end and getattr(span.style, "background", None)
    )


def test_the_entered_statuss_badge_pulses_in_its_slot_then_rests():
    clock = [100.0]
    starts = _slotted(60, [], {})[1]
    badge = group_headers.badge("merge", 1).plain

    async def check() -> None:
        app = _Bar(clock)
        async with app.run_test(size=(60, 3)):
            bar = app.query_one(AttentionBar)
            bar.observe(_active({"sam": "review"}))
            bar.observe(_active({"sam": "merge"}))
            assert str(bar.render()).index(badge) == starts["merge"]
            resting = _merge_badge_fill(bar)
            assert "sam" not in str(bar.render())

            clock[0] += attention_bar._PERIOD / 2
            bar._draw()
            assert _merge_badge_fill(bar) != resting

            clock[0] = 111.0
            bar._draw()
            assert _merge_badge_fill(bar) == resting
            assert bar._ticking is None

    asyncio.run(check())
