import asyncio

from lemonaid.inbox.tui.app import LemonaidApp


def _blur_with(last_activation: tuple[str, float]) -> tuple[tuple[str, float] | None, int]:
    async def check():
        app = LemonaidApp(scratch_mode=True)
        rechecks: list[None] = []
        app._recheck_pane_focus = lambda: rechecks.append(None)  # type: ignore[method-assign]
        async with app.run_test(size=(50, 20)) as pilot:
            await pilot.pause()
            app._last_activation = last_activation
            rechecks.clear()
            app.on_app_blur()
            return app._last_activation, len(rechecks)

    return asyncio.run(check())


def test_a_users_blur_erases_the_first_tap_and_rechecks_pane_focus():
    assert _blur_with(("7", 0.0)) == (None, 1)  # shown long ago, so the blur is the user's


def test_a_blur_just_after_a_show_keeps_the_first_tap_and_still_rechecks():
    tap = ("7", 10**9)  # stamped in the far future: always inside the window

    assert _blur_with(tap) == (tap, 1)
