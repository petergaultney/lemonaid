"""The inbox handoff has two cancellation boundaries before any mutation."""

import asyncio
from unittest.mock import Mock

import pytest
from textual.app import App
from textual.widgets import Select

from lemonaid.config import Config
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.edits import handoff_dialog
from lemonaid.inbox.tui.edits.handoff_screens import HandoffConfirm, HandoffScreen


@pytest.mark.parametrize("recovery", [False, True])
@pytest.mark.parametrize("cancel_at", ["selection", "confirmation", "never"])
@pytest.mark.parametrize("size", [(80, 30), (80, 10), (45, 10)])
def test_selection_confirm_cancel(monkeypatch, recovery, cancel_at, size):
    monkeypatch.setattr(
        handoff_dialog, "_inspect", lambda *_: ("LemonAce.work", ("codex", "codex-low"))
    )
    start = Mock(return_value={"phase": "requested", "token": "test-token"})
    monkeypatch.setattr(handoff_dialog, "_start", start)

    async def run():
        app = App()
        async with app.run_test(size=size) as pilot:
            handoff_dialog.open_dialog(app, "claude:old", Config())
            await pilot.pause()
            assert isinstance(app.screen, HandoffScreen)
            if cancel_at == "selection":
                if size[1] == 10:
                    app.screen.query_one("#cancel").scroll_visible(animate=False)
                    await pilot.pause()
                    await pilot.click("#cancel")
                else:
                    await pilot.press("escape")
            else:
                app.screen.query_one("#destination", Select).value = "codex-low"
                app.screen.query_one("#handoff-mode", Select).value = (
                    "recovery" if recovery else "cooperative"
                )
                app.screen.query_one("#review").scroll_visible(animate=False)
                await pilot.pause()
                await pilot.click("#review")
                await pilot.pause()
                assert isinstance(app.screen, HandoffConfirm)
                assert app.screen.source == "LemonAce.work"
                assert app.screen.destination == "codex-low"
                start.assert_not_called()
                if cancel_at == "confirmation":
                    if size[1] == 10:
                        app.screen.query_one("#cancel").scroll_visible(animate=False)
                        await pilot.pause()
                        await pilot.click("#cancel")
                    else:
                        await pilot.press("escape")
                else:
                    app.screen.query_one("#confirm").scroll_visible(animate=False)
                    await pilot.pause()
                    assert await pilot.click("#confirm")
            await pilot.pause()
            for worker in list(app.workers):
                if worker.group == "handoff":
                    await worker.wait()

    asyncio.run(run())
    if cancel_at == "never":
        start.assert_called_once_with("claude:old", "LemonAce.work", "codex-low", recovery)
    else:
        start.assert_not_called()


def test_top_inbox_shortcut_scrolls_buttons_into_view(monkeypatch):
    with db.connect() as conn:
        row = db.add(conn, "claude:source", "Source", status="read")
    monkeypatch.setattr(handoff_dialog, "_inspect", lambda *_: ("LemonAce.work", ("codex",)))
    start = Mock(return_value={"phase": "requested", "token": "test-token"})
    monkeypatch.setattr(handoff_dialog, "_start", start)

    async def run():
        app = LemonaidApp()
        monkeypatch.setattr(app, "_selected_notification", lambda: row)
        async with app.run_test(size=(80, 10)) as pilot:
            await pilot.press("alt+h")
            await pilot.pause()
            assert isinstance(app.screen, HandoffScreen)
            app.screen.query_one("#handoff-mode", Select).value = "recovery"
            app.screen.query_one("#review").focus()
            await pilot.wait_for_scheduled_animations()
            await pilot.pause()
            await pilot.click("#review")
            await pilot.pause()
            assert isinstance(app.screen, HandoffConfirm)
            app.screen.query_one("#confirm").focus()
            await pilot.wait_for_scheduled_animations()
            await pilot.pause()
            assert await pilot.click("#confirm")
            await pilot.pause()
            for worker in list(app.workers):
                if worker.group == "handoff":
                    await worker.wait()

    asyncio.run(run())
    start.assert_called_once_with("claude:source", "LemonAce.work", "codex", True)
