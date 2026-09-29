"""Selecting a row whose pane is gone, and whose directory is gone too.

Nothing can be switched to or recreated, so the error offers to archive the row
rather than leave it in the inbox to fail again.
"""

import asyncio

from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.error_screen import ErrorScreen


def _dead_row() -> db.Notification:
    with db.connect() as conn:
        return db.add(
            conn,
            "codex:01a0ee30-a636-7e50-9119-c4e7e5cc8af9",
            "waiting",
            "reviewer",
            {"cwd": "/gone/review", "session_id": "01a0ee30"},
            switch_source="tmux",
        )


def _select_then_press(monkeypatch, key: str) -> tuple[type, str]:
    notification = _dead_row()
    monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)
    monkeypatch.setattr("lemonaid.inbox.tui.app.handle_notification", lambda *a, **k: False)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 20)) as pilot:
            await pilot.pause()
            app._switch_to_notification(notification)
            await pilot.pause()
            shown = type(app.screen)
            await pilot.press(key)
            await pilot.pause()
            return shown

    shown = asyncio.run(run())
    with db.connect() as conn:
        return shown, db.get(conn, notification.id).status


def test_a_archives_the_row(monkeypatch):
    assert _select_then_press(monkeypatch, "a") == (ErrorScreen, "archived")


def test_any_other_key_just_closes(monkeypatch):
    assert _select_then_press(monkeypatch, "x") == (ErrorScreen, "unread")
