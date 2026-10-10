"""The follow hook's wake key moves the here-marker at once, not on the next focus poll."""

import asyncio

from lemonaid.inbox.tui import app as app_mod
from lemonaid.inbox.tui.app import LemonaidApp

from .test_brief_navigation import _lemons, _until


def test_the_wake_key_asks_tmux_which_pane_is_focused(monkeypatch, tmp_path):
    _lemons(monkeypatch, tmp_path, 2)
    focused = {"ttys": {"/dev/test-0"}}
    monkeypatch.setattr(app_mod.navigation, "focused_ttys", lambda socket=None: focused["ttys"])
    monkeypatch.setattr(app_mod, "_FOCUS_CACHE_SECONDS", 3600.0)

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await _until(pilot, lambda: app._focused == frozenset({"/dev/test-0"}))

            focused["ttys"] = {"/dev/test-1"}
            await pilot.press("f12")
            await _until(pilot, lambda: app._focused == frozenset({"/dev/test-1"}))

    asyncio.run(check())


def test_the_cursor_follows_a_focus_change_made_outside_the_inbox(monkeypatch, tmp_path):
    _lemons(monkeypatch, tmp_path, 3)
    focused = {"ttys": {"/dev/test-0"}}
    monkeypatch.setattr(app_mod.navigation, "focused_ttys", lambda socket=None: focused["ttys"])
    monkeypatch.setattr(app_mod, "_FOCUS_CACHE_SECONDS", 3600.0)

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 40)) as pilot:
            await _until(pilot, lambda: app._focused == frozenset({"/dev/test-0"}))
            table = app.query_one("#main_table")
            await _until(pilot, lambda: table.row_count == 3 and table.cursor_coordinate.row == 0)

            focused["ttys"] = {"/dev/test-2"}
            await pilot.press("f12")
            await _until(pilot, lambda: table.cursor_coordinate.row == 2)

    asyncio.run(check())
