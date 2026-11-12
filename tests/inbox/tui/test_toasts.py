"""`notify` in lma draws a toast. A method of LemonaidApp named like one of Textual's
private ones once replaced Textual's, and every toast was recorded but never drawn."""

import asyncio

from textual.widgets._toast import Toast

from lemonaid.inbox.tui.app import LemonaidApp


def test_notify_draws_a_toast():
    async def run() -> list[str]:
        app = LemonaidApp()
        async with app.run_test(size=(120, 40), notifications=True) as pilot:
            await pilot.pause()
            app.notify("Saved task.md")
            await pilot.pause()
            return [str(toast.render()) for toast in app.screen.query(Toast)]

    toasts = asyncio.run(run())

    assert any("Saved task.md" in toast for toast in toasts)
