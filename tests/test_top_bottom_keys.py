"""Ctrl+A and Ctrl+E, and Home and End, move to the top and bottom of the list."""

import asyncio
import itertools

from textual.widgets import DataTable, Input

from lemonaid import config as config_mod
from lemonaid import keys
from lemonaid.inbox import db, pins
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.help_screen import help_lines

_ids = itertools.count(900)


def _active(name: str) -> db.Notification:
    with db.connect() as conn:
        n = db.add(
            conn,
            f"claude:{name}",
            "a message",
            name,
            {"tty": f"/dev/ttys{next(_ids)}", "cwd": "/tmp", "session_id": f"s{next(_ids)}"},
        )
        conn.execute("UPDATE notifications SET switch_source = 'tmux' WHERE id = ?", (n.id,))
        conn.commit()
        return n


def _run(steps, monkeypatch, cfg: config_mod.Config | None = None):
    if cfg is not None:
        monkeypatch.setattr("lemonaid.inbox.tui.app.load_config", lambda: cfg)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def _cursor_after(presses: list[str]):
    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        rows = []
        for key in presses:
            await pilot.press(key)
            await pilot.pause()
            rows.append(table.cursor_coordinate.row)
        return table.row_count, rows

    return steps


def test_ctrl_e_goes_to_the_last_row_and_ctrl_a_to_the_first(monkeypatch):
    for i in range(4):
        _active(f"tb-{i}")

    count, rows = _run(_cursor_after(["ctrl+e", "ctrl+a"]), monkeypatch)

    assert count == 4
    assert rows == [3, 0]


def test_home_and_end_do_the_same(monkeypatch):
    for i in range(4):
        _active(f"he-{i}")

    count, rows = _run(_cursor_after(["end", "home"]), monkeypatch)

    assert rows == [count - 1, 0]


def test_the_top_is_a_pinned_row(monkeypatch):
    for i in range(3):
        _active(f"pin-{i}")
    with db.connect() as conn:
        pins.pin(conn, _active("pin-last").channel)

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        await pilot.press("ctrl+e", "ctrl+a")
        await pilot.pause()
        key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        with db.connect() as conn:
            return db.get(conn, int(key.value)).channel

    assert _run(steps, monkeypatch) == "claude:pin-last"


def test_a_rebound_key_moves_and_home_still_does(monkeypatch):
    for i in range(3):
        _active(f"rb-{i}")
    cfg = config_mod.Config()
    cfg.tui.keybindings.first = "ctrl+t"
    cfg.tui.keybindings.last = "ctrl+b"

    _, rows = _run(_cursor_after(["ctrl+b", "ctrl+t", "end", "home"]), monkeypatch, cfg)

    assert rows == [2, 0, 2, 0]


def test_a_search_box_keeps_ctrl_a_for_its_text(monkeypatch):
    for i in range(3):
        _active(f"in-{i}")

    async def steps(app, pilot):
        await pilot.press("h", "slash")
        await pilot.pause()
        box = app.query_one("#history_filter", Input)
        await pilot.press("a", "b", "ctrl+a")
        await pilot.pause()
        return app.focused is box, box.cursor_position

    focused, position = _run(steps, monkeypatch)

    assert focused
    assert position == 0


def test_the_keys_are_checked_for_conflicts():
    kb = config_mod.KeybindingsConfig(first="u")

    assert keys.conflicts(kb) == ["in the inbox view, 'u' is bound to jump_unread and first"]


def test_the_help_lists_both_spellings():
    entries = {
        desc: k for _t, rows in help_lines(config_mod.KeybindingsConfig()) for k, desc in rows
    }

    assert entries["Move to the top of the list"] == "Ctrl+a / Home"
    assert entries["Move to the bottom of the list"] == "Ctrl+e / End"
