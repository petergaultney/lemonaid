"""A click on the brief view's attention bar opens the grove, as the grove hotkey does."""

import asyncio

from textual.widgets import ContentSwitcher

from lemonaid.grove.tui.screen import GroveScreen
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.briefs.attention_bar import AttentionBar

from ..shared import lemons


def test_clicking_the_brief_views_bar_opens_the_grove(monkeypatch, tmp_path):
    lemons(monkeypatch, tmp_path, 2)
    monkeypatch.delenv("TMUX", raising=False)  # the grove opens in the app, not in a popup

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            app.action_brief()
            await pilot.pause()
            assert app.query_one(ContentSwitcher).current == "brief_view"
            await pilot.click(AttentionBar)
            await pilot.pause()
            assert isinstance(app.screen, GroveScreen)

    asyncio.run(check())
