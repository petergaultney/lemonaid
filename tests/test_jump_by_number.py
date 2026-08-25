"""Jumping to a session by its number.

The list is numbered from the top, so a row's digit is its position and nothing
more: it changes when the list reorders, and it survives no refresh. That is the
whole contract, and these tests pin the edges of it - the tenth row, the eleventh
that has no digit, and the digit typed into a search box that must stay a digit.
"""

import asyncio
import itertools

from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.utils import jump_digit, jump_gutter

_ids = itertools.count(700)


def _active(name: str) -> int:
    """A live session in the main table, switchable from this environment."""
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
        return n.id


def _run(steps, size=(120, 40), monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(LemonaidApp, "_archive_channel", lambda self, channel: None)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.pause()
            return await steps(app, pilot)

    return asyncio.run(run())


def test_the_tenth_row_is_zero_and_the_eleventh_has_no_digit():
    assert jump_digit(0) == "1"
    assert jump_digit(8) == "9"
    assert jump_digit(9) == "0"
    assert jump_digit(10) == ""


def test_an_unnumbered_row_still_pads_so_names_stay_aligned():
    assert jump_gutter(0).plain == "1 "
    assert len(jump_gutter(10).plain) == len(jump_gutter(0).plain)


def test_the_digit_prefixes_the_name(monkeypatch):
    for i in range(3):
        _active(f"jump-name-{i}")

    async def steps(app, pilot):
        from textual.widgets import DataTable

        table = app.query_one("#main_table", DataTable)
        return [table.get_row_at(r)[3].plain for r in range(min(3, table.row_count))]

    names = _run(steps, monkeypatch=monkeypatch)
    assert names, "no rows rendered"
    assert names[0].startswith("1 ")


def test_a_digit_past_the_last_row_does_nothing(monkeypatch):
    _active("jump-only-one")

    async def steps(app, pilot):
        from textual.widgets import DataTable

        table = app.query_one("#main_table", DataTable)
        before = table.cursor_coordinate.row
        app.action_jump_to_number("0")
        return before, table.cursor_coordinate.row

    before, after = _run(steps, monkeypatch=monkeypatch)
    assert before == after


def test_a_digit_selects_the_row_at_that_position(monkeypatch):
    """The jump lands on the row and then acts on it, as Enter would."""
    for i in range(3):
        _active(f"jump-move-{i}")

    selected: list[int] = []

    async def steps(app, pilot):
        from textual.widgets import DataTable

        table = app.query_one("#main_table", DataTable)
        monkeypatch.setattr(
            LemonaidApp,
            "action_select",
            lambda self: selected.append(table.cursor_coordinate.row),
        )
        app.action_jump_to_number("2")
        return table.cursor_coordinate.row

    row = _run(steps, monkeypatch=monkeypatch)
    assert row == 1
    assert selected == [1], "the row was moved to but never selected"


def test_a_digit_typed_into_the_history_filter_stays_a_digit(monkeypatch):
    """The filter is a text box; a digit there is search input, not a jump."""

    async def steps(app, pilot):
        from textual.widgets import Input

        app._set_history_mode(True)
        await pilot.pause()
        app.action_filter_history()
        await pilot.pause()
        filter_input = app.query_one("#history_filter", Input)
        filter_input.focus()
        await pilot.pause()
        await pilot.press("3")
        await pilot.pause()
        return filter_input.value

    assert _run(steps, monkeypatch=monkeypatch) == "3"
