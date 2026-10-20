"""Brief transitions while inbox work is still queued."""

import asyncio

from textual.widgets import DataTable, Input

from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.briefs.brief_pane import BriefPane
from lemonaid.inbox.tui.edits.screens import SnoozeScreen

from ..shared import lemons


def test_brief_opens_and_closes_while_a_dialog_has_focus(monkeypatch, tmp_path):
    _, state = lemons(monkeypatch, tmp_path, 2)

    async def check():
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await app.push_screen(SnoozeScreen())
            await pilot.pause()
            assert isinstance(app.focused, Input)
            pane = app.query_one(BriefPane)
            app.call_later(pane.set_view, state["targets"][0])
            await pilot.pause()
            app.call_later(pane.set_view, None)
            await pilot.pause()
            assert isinstance(app.focused, Input)
            await pilot.press("escape")
            await pilot.pause()
            assert app.focused is app.query_one("#main_table", DataTable)

    asyncio.run(check())


def test_repeated_brief_transitions_with_queued_refreshes(monkeypatch, tmp_path):
    _, state = lemons(monkeypatch, tmp_path, 3)

    async def check():
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            pane = app.query_one(BriefPane)
            for index in range(30):
                pane.set_view(state["targets"][index % 3])
                app._refresh_notifications()
                pane.action_question(1)
                app.call_later(pane.set_view, None)
                await pilot.pause(0.001)
            assert app.is_running

    asyncio.run(check())
