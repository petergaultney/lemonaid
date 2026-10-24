"""Search ends only after reaching a lemon, when configured."""

import asyncio

import pytest
from textual.widgets import DataTable, Input

from lemonaid.config import InboxConfig, _parse_config
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.switching import history_resume, inbox_switch


def _add(channel: str, name: str, status: str = "unread") -> None:
    with db.connect() as conn:
        db.add(conn, channel, "message", name, {"cwd": "/tmp"}, status=status, switch_source="tmux")


@pytest.fixture(autouse=True)
def _terminal(monkeypatch):
    monkeypatch.setattr("lemonaid.inbox.tui.app.detect_terminal_switch_source", lambda: "tmux")


def _assert_search(app: LemonaidApp, *, open: bool) -> None:
    assert app._search_mode is open
    assert app._content.filter_text == ("match" if open else "")
    box = app.query_one("#history_filter", Input)
    assert box.display is open
    assert box.value == ("match" if open else "")
    assert app.query_one("#main_table", DataTable).row_count == (1 if open else 2)
    if not open:
        assert not app.query_one("#history_table", DataTable).display
        assert app.sub_title == "attention inbox"


@pytest.mark.parametrize("setting", [None, True, False])
def test_config(setting):
    data = {} if setting is None else {"inbox": {"close_search_on_switch": setting}}
    assert _parse_config(data).inbox.close_search_on_switch is (setting is not False)
    assert InboxConfig().close_search_on_switch is True


@pytest.mark.parametrize("close", [True, False])
@pytest.mark.parametrize("success", [True, False])
@pytest.mark.parametrize("archived", [True, False])
def test_enter_switch(monkeypatch, close, success, archived):
    _add("claude:match", "match", "archived" if archived else "unread")
    _add("claude:other", "other")
    switched = []
    monkeypatch.setattr(
        inbox_switch,
        "handle_notification",
        lambda *args, **kwargs: switched.append(args) or success,
    )
    monkeypatch.setattr("lemonaid.resume.build_resume_command", lambda *args: None)
    monkeypatch.setattr("lemonaid.inbox.unarchive.running", lambda notification: True)

    async def run():
        app = LemonaidApp()
        app.config.inbox.close_search_on_switch = close
        async with app.run_test(size=(120, 35)) as pilot:
            for key in ("/", "m", "a", "t", "c", "h", "enter", "enter"):
                await pilot.press(key)
                await pilot.pause()
            assert len(switched) == 1
            _assert_search(app, open=not (close and success))

    asyncio.run(run())


@pytest.mark.parametrize("close", [True, False])
@pytest.mark.parametrize("kind", ["started", "failed", "unresumable", "copy"])
def test_enter_resume(monkeypatch, close, kind):
    _add("claude:archived", "match archived", "archived")
    _add("claude:match", "match")
    _add("claude:other", "other")
    monkeypatch.setattr(
        history_resume, "run", lambda *args: history_resume.Outcome(kind, "resume", "failed")
    )
    monkeypatch.setattr(inbox_switch, "copy_resume", lambda *args: None)
    monkeypatch.setattr(LemonaidApp, "_hide_scratch_pane", lambda self: None)

    async def run():
        app = LemonaidApp()
        app.config.inbox.close_search_on_switch = close
        app._scratch_mode = True
        async with app.run_test(size=(120, 35)) as pilot:
            for key in ("/", "m", "a", "t", "c", "h", "enter", "down", "enter"):
                await pilot.press(key)
                await pilot.pause()
            _assert_search(app, open=not (close and kind == "started"))

    asyncio.run(run())
