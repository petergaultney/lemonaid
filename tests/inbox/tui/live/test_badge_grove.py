"""In attention mode, a click on a group header's status badge opens that group's grove block."""

import asyncio
import itertools
import os
import subprocess
import time
from pathlib import Path

import pytest

from lemonaid import groups
from lemonaid.brief import attached
from lemonaid.brief import store as brief_store
from lemonaid.grove.source import inbox_keys
from lemonaid.grove.tui.screen import GroveScreen
from lemonaid.inbox import attention, db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.tables.table import ClickToActTable
from lemonaid.inbox.tui.watchers import watcher_hooks
from lemonaid.tmux import fast_popup

_ids = itertools.count(1300)


@pytest.fixture(autouse=True)
def _inbox(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher_hooks, "archive_channel", lambda channel: None)
    monkeypatch.setenv("LEMONAID_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("TMUX")  # the grove opens in the inbox, not in a popup
    Path(os.environ["LEMONAID_CONFIG"]).write_text("")


def _grouped(name: str, status: str, group: str) -> str:
    channel = f"claude:{name}"
    with db.connect() as conn:
        n = db.add(
            conn,
            channel,
            "a message",
            name,
            {"tty": f"/dev/ttys{next(_ids)}", "cwd": "/tmp", "session_id": f"s{next(_ids)}"},
        )
        conn.execute(
            "UPDATE notifications SET switch_source = 'tmux', status = 'read', created_at = ?"
            " WHERE id = ?",
            (time.time(), n.id),
        )
        path = brief_store.briefs_dir() / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# work\n\nStatus: {status}\n\n## Now\n")
        attached.attach(conn, channel, path)
        try:
            found = groups.store.find(conn, group)
        except LookupError:
            found = groups.store.create(conn, group)
        groups.store.add(conn, found, [channel])
        conn.commit()
    return channel


def _badge_at(table: ClickToActTable, status: str) -> tuple[int, int] | None:
    """Where *status*'s badge is drawn in *table*, by its click meta."""
    for y in range(table.size.height):
        x = 0
        for segment in table.render_line(y):
            if segment.style and segment.style.meta.get("badge") == status:
                return x, y
            x += segment.cell_length
    return None


def _click_badge(on: bool):
    attention.save(on)
    _grouped("shipped", "done", "Kitchen")
    _grouped("waiting", "blocked", "Kitchen")

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause()
            await pilot.pause()
            table = app.query_one("#main_table", ClickToActTable)
            where = _badge_at(table, "done")
            assert where is not None, "no done badge drawn"
            digit = inbox_keys.digits(app._content.inbox.grove).get("Kitchen", "")
            await pilot.click(ClickToActTable, offset=where)
            await pilot.pause()
            screen = app.screen
            return digit, screen._where.block if isinstance(screen, GroveScreen) else None

    return asyncio.run(run())


def test_a_badge_click_in_attention_mode_opens_its_groups_block():
    digit, zoomed = _click_badge(True)

    assert digit
    assert zoomed == digit


def test_outside_attention_mode_a_badge_click_leaves_the_grove_shut():
    _, zoomed = _click_badge(False)

    assert zoomed is None


def test_the_popup_takes_its_zoom_once(monkeypatch):
    options: dict[str, str] = {}

    def tmux(*args: str) -> subprocess.CompletedProcess[str]:
        if args[0] == "set-option" and "-u" in args:
            options.pop(args[-1], None)
        elif args[0] == "set-option":
            options[args[-2]] = args[-1]
        out = options.get(args[-1], "") if args[0] == "show-option" else ""
        return subprocess.CompletedProcess(args, 0, out, "")

    monkeypatch.setattr(fast_popup, "_tmux", tmux)
    tmux("set-option", "-t", "=x:", fast_popup.ZOOM_OPTION, "3")

    assert fast_popup.take_zoom("grove") == "3"
    assert fast_popup.take_zoom("grove") == ""
