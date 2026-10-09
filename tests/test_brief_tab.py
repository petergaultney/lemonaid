"""A `brief_key` of Tab opens the brief like `b`, and is left alone in dialogs and inputs."""

import asyncio

from textual.widgets import Input

from lemonaid import config as config_mod
from lemonaid.inbox.tui import app as app_mod
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.screens import SnoozeScreen

from .test_brief_navigation import _lemons, _until


def _tab_for_briefs(monkeypatch) -> None:
    cfg = config_mod.load_config()
    cfg.tui.keybindings.brief_key = "tab"
    cfg.tui.keybindings.group_key = ""
    monkeypatch.setattr(app_mod, "load_config", lambda: cfg)


def test_tab_opens_the_brief_and_goes_back_to_the_inbox(monkeypatch, tmp_path):
    rows, state = _lemons(monkeypatch, tmp_path, 2)
    _tab_for_briefs(monkeypatch)

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.press("tab")
            await _until(pilot, lambda: app._brief_target == state["targets"][0])

            await pilot.press("tab")
            await _until(pilot, lambda: app._brief_target is None)

    asyncio.run(check())


def _briefs_opened(monkeypatch) -> list[str]:
    called: list[str] = []
    monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)
    monkeypatch.setattr(LemonaidApp, "action_brief", lambda self: called.append("brief"))
    return called


def test_an_empty_brief_key_leaves_tab_unbound(monkeypatch):
    cfg = config_mod.load_config()
    cfg.tui.keybindings.brief_key = ""
    monkeypatch.setattr(app_mod, "load_config", lambda: cfg)
    called = _briefs_opened(monkeypatch)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()

    asyncio.run(run())

    assert called == []


def test_tab_in_a_dialog_does_not_open_a_brief(monkeypatch):
    _tab_for_briefs(monkeypatch)
    called = _briefs_opened(monkeypatch)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(SnoozeScreen())
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            assert isinstance(app.screen, SnoozeScreen)

    asyncio.run(run())

    assert called == []


def test_tab_in_the_history_filter_does_not_open_a_brief(monkeypatch):
    _tab_for_briefs(monkeypatch)
    called = _briefs_opened(monkeypatch)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.action_toggle_history()
            app.action_filter_history()
            await pilot.pause()
            assert isinstance(app.focused, Input)
            await pilot.press("tab")
            await pilot.pause()

    asyncio.run(run())

    assert called == []
