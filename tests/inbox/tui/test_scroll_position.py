import asyncio

import pytest
from textual.app import App
from textual.scrollbar import ScrollTo
from textual.widgets import Static

from lemonaid.inbox.tui import scroll_position
from lemonaid.inbox.tui.tables.scroll_position import StableTable


@pytest.mark.parametrize("surface", ["markdown", "table"])
@pytest.mark.parametrize("command", ["wheel_down", "wheel_up", "drag"])
def test_pointer_scroll_supersedes_pending_restore(surface, command):
    async def check():
        app = App()
        async with app.run_test(size=(40, 15)) as pilot:
            if surface == "markdown":
                view = scroll_position.StableScroll()
                await app.mount(view)
                await view.mount(Static("\n".join(str(i) for i in range(80))))
            else:
                view = StableTable()
                await app.mount(view)
                view.add_column("Text")
                for i in range(80):
                    view.add_row(str(i), key=str(i))
            await pilot.pause()
            view.scroll_to(y=30, animate=False, immediate=True)
            await pilot.pause()
            if surface == "markdown":
                await scroll_position.replace(
                    view, [Static("\n".join(str(i) for i in range(80)))], True
                )
            else:
                with view.preserve_scroll():
                    view.clear()
                    for i in range(80):
                        view.add_row(str(i), key=str(i))
            if command == "wheel_down":
                view._scroll_down_for_pointer(animate=False)
            elif command == "wheel_up":
                view._scroll_up_for_pointer(animate=False)
            else:
                view._on_scroll_to(ScrollTo(y=45, animate=False))
            requested = view.scroll_y if command != "drag" or surface == "table" else 45
            await pilot.pause()
            assert view.scroll_y == requested

    asyncio.run(check())
