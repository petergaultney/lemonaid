import asyncio
import types

import pytest

from lemonaid.grove.tui import screen
from lemonaid.grove.tui.app import GroveApp

from .test_frame import GROVE


@pytest.fixture(autouse=True)
def _still_clock(monkeypatch):
    """The grove's clock stands still, so only the time a test moves `_backed_out_at` by passes
    between keys, however slowly they arrive."""
    monkeypatch.setattr(screen, "time", types.SimpleNamespace(monotonic=lambda: 1000.0))


def _closes(keys: list[str], waited: float = 0.0) -> list[bool]:
    """After each key, whether the grove has closed. *waited* seconds pass before the last key."""
    closed: list[bool] = []

    async def run() -> None:
        app = GroveApp(lambda: GROVE, 60.0, lambda _: "", leave=lambda: closed.append(True))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause()
            for i, key in enumerate(keys):
                if i == len(keys) - 1:
                    app.screen._backed_out_at -= waited
                await pilot.press(key)
                await pilot.pause()
                found.append(bool(closed))

    found: list[bool] = []
    asyncio.run(run())
    return found


def test_backspace_with_nothing_typed_closes_the_grove_like_esc():
    assert _closes(["backspace"]) == [True]
    assert _closes(["escape"]) == [True]


def test_backspace_right_after_backing_out_of_a_block_keeps_the_grove_open():
    assert _closes(["1", "backspace", "backspace"]) == [False, False, False]


def test_backspace_closes_the_grove_once_the_pause_has_passed():
    waited = screen._BACKSPACE_CLOSES_AFTER
    assert _closes(["1", "backspace", "backspace"], waited) == [False, False, True]
    assert _closes(["1", "backspace", "backspace"], waited - 0.2) == [False, False, False]


def test_a_held_backspace_never_closes_the_grove_however_long_it_repeats():
    repeats = ["backspace"] * 8
    found: list[bool] = []

    async def run() -> None:
        closed: list[bool] = []
        app = GroveApp(lambda: GROVE, 60.0, lambda _: "", leave=lambda: closed.append(True))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("1")
            await pilot.pause()
            for key in repeats:
                # 0.15 seconds pass between repeats
                app.screen._backed_out_at -= 0.15
                await pilot.press(key)
                await pilot.pause()
                found.append(bool(closed))

    asyncio.run(run())
    assert len(repeats) * 0.15 > screen._BACKSPACE_CLOSES_AFTER
    assert found == [False] * len(repeats)
