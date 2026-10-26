import asyncio

from lemonaid.grove.tui import flip
from lemonaid.grove.tui.app import GroveApp

from .test_frame import GROVE


def test_a_held_key_waits_out_the_repeat_delay_once_then_only_the_repeat_gap():
    assert flip.pressed(False, hold=True) == (True, flip.FIRST_WAIT)
    assert flip.pressed(True, hold=True) == (True, flip.REPEAT_WAIT)


def test_a_toggle_flips_each_press_and_never_flips_back_by_itself():
    assert flip.pressed(False, hold=False) == (True, 0.0)
    assert flip.pressed(True, hold=False) == (False, 0.0)


def _flipped_after(flips: flip.Flip, presses: list[float]) -> list[bool]:
    """Whether the lists are flipped after each press of *flips*'s key, the given seconds apart."""

    async def run() -> list[bool]:
        app = GroveApp(lambda: GROVE, 60.0, None, flips=flips)
        seen = []
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.press("1")
            for wait in presses:
                await asyncio.sleep(wait)
                await pilot.press(flips.key)
                seen.append(app.screen._flipped)
            await asyncio.sleep(flip.FIRST_WAIT + 0.1)
            await pilot.pause()
            seen.append(app.screen._flipped)
        return seen

    return asyncio.run(run())


def test_holding_the_key_keeps_the_lists_flipped_until_its_repeats_stop():
    assert _flipped_after(flip.Flip("\\"), [0.0, 0.3, 0.05, 0.05]) == [True] * 4 + [False]


def test_a_toggled_flip_stays_until_the_key_is_pressed_again():
    assert _flipped_after(flip.Flip("\\", hold=False), [0.0]) == [True, True]
    assert _flipped_after(flip.Flip("\\", hold=False), [0.0, 0.1]) == [True, False, False]
