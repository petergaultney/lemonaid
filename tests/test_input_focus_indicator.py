"""The title bar identifies the tmux pane that will receive the next key."""

import asyncio
import os
import subprocess
from pathlib import Path

import pytest
from textual.color import Color
from textual.widgets import Header

from lemonaid.inbox.tui import app as app_module
from lemonaid.inbox.tui.app import LemonaidApp, _tmux_pane_receives_keys


def test_tmux_focus_needs_selected_pane_window_and_attached_session(monkeypatch):
    def response(values):
        return subprocess.CompletedProcess([], 0, values, "")

    monkeypatch.setattr(app_module.subprocess, "run", lambda *a, **kw: response("1 1 1\n"))
    assert _tmux_pane_receives_keys("%9") is True

    for values in ("0 1 1\n", "1 0 1\n", "1 1 0\n"):
        monkeypatch.setattr(
            app_module.subprocess, "run", lambda *a, values=values, **kw: response(values)
        )
        assert _tmux_pane_receives_keys("%9") is False

    monkeypatch.setattr(app_module.subprocess, "run", lambda *a, **kw: response("not tmux"))
    assert _tmux_pane_receives_keys("%9") is None


def test_scratch_header_changes_when_tmux_focus_changes(monkeypatch):
    monkeypatch.setenv("TMUX_PANE", "%9")
    active = False
    monkeypatch.setattr(app_module, "_tmux_pane_receives_keys", lambda pane: active)

    async def check():
        nonlocal active
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 20)) as pilot:
            await pilot.pause()
            assert not app.has_class("-input-active")

            active = True
            app._input_focus_asked_at = 0
            app._refresh_notifications()
            await pilot.pause()
            assert app.has_class("-input-active")
            assert app.query_one(Header).styles.background == Color.parse("#2bd9cf")
            assert app.screen.styles.border_bottom[1] == Color.parse("#2bd9cf")

            active = False
            app._input_focus_asked_at = 0
            app._refresh_notifications()
            await pilot.pause()
            assert not app.has_class("-input-active")
            assert app.screen.styles.border_bottom[1] != Color.parse("#2bd9cf")

    asyncio.run(check())


@pytest.mark.parametrize(
    ("configured", "background", "text"),
    [
        ("#ffd000", "#ffd000", "#000000"),
        ("#102060", "#102060", "#ffffff"),
        ("not a colour", "#2bd9cf", "#000000"),
    ],
)
def test_the_focus_colour_comes_from_config(monkeypatch, configured, background, text):
    Path(os.environ["LEMONAID_CONFIG"]).write_text(f'[tui]\nfocus_color = "{configured}"\n')
    monkeypatch.setenv("TMUX_PANE", "%9")
    monkeypatch.setattr(app_module, "_tmux_pane_receives_keys", lambda pane: True)

    async def check():
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 20)) as pilot:
            await pilot.pause()
            header = app.query_one(Header)
            assert header.styles.background == Color.parse(background)
            assert header.styles.color == Color.parse(text)
            assert app.screen.styles.border_bottom[1] == Color.parse(background)

    asyncio.run(check())
