import asyncio

from lemonaid.grove.tui.app import GroveApp
from lemonaid.grove.tui.screen import GroveScreen

from .test_frame import GROVE


def test_a_grove_that_hides_keeps_running_with_a_fresh_one_held_for_next_time():
    hidden = []

    async def run() -> tuple[bool, bool, bool]:
        app = GroveApp(lambda: GROVE, 60.0, lambda _: "", leave=lambda: hidden.append(True))
        async with app.run_test(size=(160, 48)) as pilot:
            first = app.screen
            await pilot.press("escape")
            await pilot.pause()
            held = app.screen._held
            await pilot.press("1")
            await pilot.pause()
            return (
                app.screen is not first and isinstance(app.screen, GroveScreen),
                held,
                (app.screen._held),
            )

    replaced, held, still_held = asyncio.run(run())
    assert hidden == [True]
    assert replaced and held and not still_held
