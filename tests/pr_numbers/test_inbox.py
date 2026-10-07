import asyncio
import threading

import pytest

from lemonaid.config import PlaceRoot
from lemonaid.inbox import db
from lemonaid.inbox.tui import app, pr_numbers
from lemonaid.tmux import scratch


@pytest.mark.parametrize("position,size", [("top", (160, 12)), ("left", (60, 36))])
def test_hook_number_reaches_both_layouts_without_blocking(monkeypatch, tmp_path, position, size):
    scratch.set_position(position)
    entered = threading.Event()
    release = threading.Event()
    calls = []
    ui_thread = threading.get_ident()

    def lookup(root):
        calls.append(threading.get_ident())
        entered.set()
        assert release.wait(5)
        return {"topic": "123"}

    monkeypatch.setattr(pr_numbers, "refresh", lookup)
    with db.connect() as conn:
        for index in range(2):
            db.add(
                conn,
                f"codex:task{index}",
                "message",
                f"task{index}",
                {"cwd": str(tmp_path), "git_branch": "topic"},
                switch_source="tmux",
                status="read",
            )

    async def check():
        tui = app.LemonaidApp(scratch_mode=True)
        tui.config.places.roots = [PlaceRoot(tmp_path, open_prs="lookup")]
        tui.config.tui.brief_status = False
        async with tui.run_test(size=size) as pilot:
            await pilot.pause()
            assert entered.is_set()
            table = tui.query_one("#main_table", app.ClickToActTable)
            assert table.row_count == 2
            assert all("#123" not in str(table.get_row_at(i)) for i in range(2))
            tui._refresh_notifications()
            assert len(calls) == 1
            assert calls[0] != ui_thread
            release.set()
            await pilot.pause()
            for i in range(2):
                assert "#123" in " ".join(cell.plain for cell in table.get_row_at(i))
            assert len(calls) == 1

    try:
        asyncio.run(check())
    finally:
        release.set()


def test_number_precedes_long_name_and_keeps_emoji_prefix():
    notification = db.Notification(
        id=1,
        channel="codex:task",
        message="",
        name="a long task name",
        metadata={},
        status="read",
        created_at=0,
    )
    text = app._name_cell(notification, {"codex:task": "X"}, "Name", False, "123")
    assert text.plain == "X #123 a long task name · Name"
