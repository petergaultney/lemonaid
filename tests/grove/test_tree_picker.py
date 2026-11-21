import asyncio

from textual.app import App
from textual.containers import Vertical

from lemonaid.grove.source.tree_picker import TreePickerScreen

_TREES = (("", "back to its own tree"), ("claude:a", "5r richer"), ("claude:b", "5g window"))


def _picked(*keys: str) -> list[str | None]:
    async def run() -> list[str | None]:
        chosen: list[str | None] = []
        app: App = App()
        async with app.run_test(size=(120, 24)) as pilot:
            app.push_screen(TreePickerScreen("Put lemon on another tree", _TREES), chosen.append)
            await pilot.pause()
            assert app.screen.query_one(Vertical).region.width == 60  # the group picker's box
            await pilot.press(*keys)
            await pilot.pause()
        return chosen

    return asyncio.run(run())


def test_typing_narrows_the_trees_enter_takes_the_first_and_escape_cancels():
    assert _picked("w", "i", "n", "enter") == ["claude:b"]
    assert _picked("down", "enter") == ["claude:a"]
    assert _picked("enter") == [""]
    assert _picked("escape") == [None]
