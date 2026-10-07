"""Queued table messages can outlive the widgets during app shutdown."""

import asyncio

from textual.widgets import DataTable

from lemonaid.inbox.tui.app import LemonaidApp


def test_a_row_highlight_after_tables_are_removed_during_shutdown(monkeypatch):
    async def run():
        app = LemonaidApp()
        close_all = app._close_all
        delivered = []

        async with app.run_test() as pilot:
            table = app.query_one("#main_table", DataTable)
            key = table.add_row("", "", "", "", "", "", key="1")
            event = DataTable.RowHighlighted(table, 0, key)
            await pilot.pause()

            async def close_and_highlight():
                await close_all()
                assert not app.is_running
                assert not app.query("#main_table")
                await app._dispatch_message(event)
                delivered.append(event)

            monkeypatch.setattr(app, "_close_all", close_and_highlight)

        assert delivered == [event]

    asyncio.run(run())
