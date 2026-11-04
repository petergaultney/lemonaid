import asyncio

from textual.screen import ModalScreen

from lemonaid.config import load_config
from lemonaid.grove.source import inbox_screen
from lemonaid.grove.tui import help_panel
from lemonaid.grove.tui.app import GroveApp
from lemonaid.grove.tui.screen import GroveScreen, Overlay
from lemonaid.inbox.tui.views.usage_screen import UsageScreen

from .test_frame import GROVE


class _Overlay(ModalScreen[None]):
    BINDINGS = [("U", "dismiss", "Close")]


def _screens(*presses: str) -> list[type]:
    async def run() -> list[type]:
        app = GroveApp(
            lambda: GROVE,
            60.0,
            None,
            leave=lambda: None,
            overlays={"U": Overlay("open it", _Overlay)},
        )
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause()
            await pilot.press(*presses)
            await pilot.pause()
            return [type(screen) for screen in app.screen_stack[1:]]

    return asyncio.run(run())


def test_an_overlay_key_opens_its_screen_over_the_grove_and_closes_it():
    assert _screens("U") == [GroveScreen, _Overlay]
    assert _screens("2", "U") == [GroveScreen, _Overlay]
    assert _screens("U", "U") == [GroveScreen]


def test_an_overlay_key_is_typed_into_a_search():
    assert _screens("/", "U") == [GroveScreen]


def test_the_inboxs_grove_opens_usage_on_the_usage_key():
    config = load_config()
    screen = inbox_screen.for_inbox(lambda: None, config)

    assert isinstance(screen._overlays[config.tui.keybindings.usage_view].open(), UsageScreen)


def test_the_help_panel_lists_the_overlay_keys():
    assert dict(help_panel.rows(False, more=[("U", "open it")]))["U"] == "open it"
