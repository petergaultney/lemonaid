"""A click on the attention bar, in the inbox or the brief view, opens the grove like its hotkey."""

import asyncio
import os
from pathlib import Path

import pytest

from lemonaid.grove.tui.screen import GroveScreen
from lemonaid.inbox import attention
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.watchers import watcher_hooks

from .test_badge_grove import _grouped


@pytest.fixture(autouse=True)
def _inbox(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher_hooks, "archive_channel", lambda channel, why: None)
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("TMUX")  # the grove opens in the inbox, not in a popup


def _click(selector: str, *, config: str = "") -> bool:
    Path(os.environ["LEMONAID_CONFIG"]).write_text(config)
    attention.save(True)
    _grouped("shipped", "done", "Kitchen")

    async def run() -> bool:
        app = LemonaidApp()
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.click(selector)
            await pilot.pause()
            return isinstance(app.screen, GroveScreen)

    return asyncio.run(run())


def test_clicking_the_inbox_bar_opens_the_grove():
    assert _click("#attention_summary")


def test_with_the_grove_key_unset_a_click_on_the_bar_does_nothing():
    assert not _click("#attention_summary", config='[tui.keybindings]\ngrove = ""\n')
