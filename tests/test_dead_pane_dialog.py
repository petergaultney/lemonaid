"""A row without a resume command offers a persistent explanation and archive action."""

import asyncio

from textual.containers import Vertical
from textual.widgets import Label

from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.resume_error import ResumeErrorScreen


def _dead_row() -> db.Notification:
    with db.connect() as conn:
        return db.add(
            conn,
            "unknown:01a0ee30-a636-7e50-9119-c4e7e5cc8af9",
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
    assert _select_then_press(monkeypatch, "a") == (ResumeErrorScreen, "archived")


def test_escape_closes_without_archiving(monkeypatch):
    assert _select_then_press(monkeypatch, "escape") == (ResumeErrorScreen, "unread")


def test_arrow_keys_do_not_dismiss_resume_failure(monkeypatch):
    row = _dead_row()
    monkeypatch.setattr("lemonaid.inbox.tui.app.handle_notification", lambda *a, **k: False)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(50, 30)) as pilot:
            app._switch_to_notification(row)
            await pilot.pause()
            screen = app.screen
            await pilot.press("down", "up", "x")
            assert app.screen is screen
            await pilot.press("escape")
            assert app.screen is not screen

    asyncio.run(run())


def test_missing_directory_without_tmux_destination_shows_fallback_command(monkeypatch, tmp_path):
    with db.connect() as conn:
        row = db.add(
            conn,
            "codex:id",
            "waiting",
            "detached",
            {"cwd": str(tmp_path / "gone"), "session_id": "id"},
            switch_source="tmux",
        )
    monkeypatch.setattr("lemonaid.inbox.tui.app.handle_notification", lambda *a, **k: False)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(50, 30)) as pilot:
            app._set_detached_channels({row.channel})
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ResumeErrorScreen)
            assert str(tmp_path / "gone") in app.screen._details
            assert "codex resume id --cd" in app.screen._details
            assert str(tmp_path) in app.screen._details
            await pilot.press("down", "up")
            assert isinstance(app.screen, ResumeErrorScreen)
            await pilot.press("escape")

    asyncio.run(run())
    assert not (tmp_path / "gone").exists()


def test_resume_error_wraps_and_scrolls_long_instructions():
    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(40, 15)) as pilot:
            details = "cd /a/long/directory && codex resume session-id --cd /a/long/directory\n" * 8
            app.push_screen(
                ResumeErrorScreen(
                    "Cannot resume here",
                    "Choose a session and run the displayed command.",
                    details=details,
                )
            )
            await pilot.pause()
            screen = app.screen
            assert screen.query_one(".details", Label).size.height > 1
            container = screen.query_one(Vertical)
            assert container.max_scroll_y > 0
            await pilot.press("pagedown")
            assert app.screen is screen
            assert container.scroll_y > 0
            await pilot.press("escape")

    asyncio.run(run())
