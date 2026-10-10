"""External jumps must leave the scratch inbox able to return to its selected row."""

import asyncio

import pytest

from lemonaid.inbox import db
from lemonaid.inbox.tui import app as app_mod
from lemonaid.inbox.tui.table import ClickToActTable
from lemonaid.inbox.tui.utils import HERE_BLOCK
from lemonaid.tmux import navigation

from .shared import run
from .shared_tmux import _query, _record


def test_external_jump_has_only_the_target_green(server, clients, monkeypatch):
    sender = _record(server, "source:0")
    _query(server, "split-window", "-d", "-t", "source")
    target = _record(server, "source:0.1")
    scratch = _query(server, "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", "source")
    _query(server, "set-option", "-p", "-t", scratch, "@lemonaid_scratch", "1")
    clients("source")
    monkeypatch.setenv("TMUX", f"{server[2]},0,0")
    monkeypatch.setenv("TMUX_PANE", scratch)
    _query(server, "select-pane", "-t", sender.metadata["tmux_pane_identity"][0])
    run("codex:real")
    assert navigation.focused_ttys(server[2]) == {target.metadata["tty"]}


@pytest.mark.parametrize("action", ["click", "enter", "marker"])
def test_selecting_sender_after_external_jump_returns_to_it(server, clients, monkeypatch, action):
    sender = _record(server, "source:0")
    with db.connect() as conn:
        db.add(conn, "codex:sender", "", "sender", sender.metadata, switch_source="tmux")
        sender = db.get_by_channel(conn, "codex:sender")
    _query(server, "split-window", "-d", "-t", "source")
    target = _record(server, "source:0.1")
    with db.connect() as conn:
        old = db.add(
            conn,
            "codex:old-target",
            "",
            "old target",
            target.metadata,
            switch_source="tmux",
            created_at=target.created_at - 60,
        )
    scratch = _query(server, "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", "source")
    _query(server, "set-option", "-p", "-t", scratch, "@lemonaid_scratch", "1")
    clients("source")
    monkeypatch.setenv("TMUX", f"{server[2]},0,0")
    monkeypatch.setenv("TMUX_PANE", scratch)
    monkeypatch.setattr(app_mod, "start_unified_watcher", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_mod, "is_follow_enabled", lambda: True)
    monkeypatch.setattr(app_mod, "current_position", lambda _: "top")

    async def check():
        app = app_mod.LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(300, 35)) as pilot:
            table = app.query_one("#main_table", ClickToActTable)
            row = table.get_row_index(str(sender.id))
            table.move_cursor(row=row)
            _query(server, "select-pane", "-t", sender.metadata["tmux_pane_identity"][0])
            run("codex:real")
            assert _query(server, "list-clients", "-F", "#{pane_tty}") == target.metadata["tty"]
            app._focused_asked_at = 0
            app._refresh_notifications()
            if action == "marker":
                assert table.get_row(str(target.id))[3].plain.startswith(HERE_BLOCK)
                assert not table.get_row(str(old.id))[3].plain.startswith(HERE_BLOCK)
                return
            assert table.cursor_coordinate.row == table.get_row_index(str(target.id))
            row = table.get_row_index(str(sender.id))
            table.move_cursor(row=row)
            _query(server, "select-pane", "-t", scratch)
            app._input_focus_asked_at = 0
            app._update_input_indicator()
            assert app.has_class("-input-active")
            if action == "click":
                await pilot.click("#main_table", offset=(10, 1 + row))
            else:
                await pilot.press("enter")
            await pilot.pause()
            assert _query(server, "list-clients", "-F", "#{pane_tty}") == sender.metadata["tty"]
            # Reclicking the current lemon keeps focus in scratch; Enter still returns.
            _query(server, "select-pane", "-t", scratch)
            app._input_focus_asked_at = 0
            app._update_input_indicator()
            await pilot.click("#main_table", offset=(10, 1 + row))
            await pilot.pause()
            assert _query(server, "list-clients", "-F", "#{pane_id}") == scratch
            await pilot.press("enter")
            await pilot.pause()
            assert _query(server, "list-clients", "-F", "#{pane_tty}") == sender.metadata["tty"]

    asyncio.run(check())
