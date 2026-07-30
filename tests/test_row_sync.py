"""Tests for in-place table updates.

Rebuilding the table on every refresh tick reset the cursor and scroll offset,
which presented as the row list flashing to the top once a second.
"""

import asyncio

from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import DataTable

from lemonaid.inbox.tui.app import _sync_rows


class _TableApp(App):
    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_column("a")
        table.add_column("b")


def _rows(*specs: tuple[str, str]) -> list[tuple[str, list[Text]]]:
    return [(key, [Text(key), Text(value)]) for key, value in specs]


def _run(body):
    async def main():
        app = _TableApp()
        async with app.run_test(size=(40, 10)) as pilot:
            await pilot.pause()
            return await body(app.query_one(DataTable), pilot)

    return asyncio.run(main())


def test_same_row_set_updates_in_place():
    async def body(table, pilot):
        _sync_rows(table, _rows(("1", "one"), ("2", "two")))
        await pilot.pause()
        rebuilt = _sync_rows(table, _rows(("1", "ONE"), ("2", "two")))
        return rebuilt, table.get_row("1")[1].plain, table.row_count

    rebuilt, cell, count = _run(body)
    assert rebuilt is False
    assert cell == "ONE"
    assert count == 2


def test_cursor_survives_in_place_update():
    async def body(table, pilot):
        _sync_rows(table, _rows(("1", "a"), ("2", "b"), ("3", "c")))
        await pilot.pause()
        table.move_cursor(row=2)
        await pilot.pause()
        _sync_rows(table, _rows(("1", "a"), ("2", "CHANGED"), ("3", "c")))
        await pilot.pause()
        return table.cursor_coordinate.row

    assert _run(body) == 2


def test_changed_row_set_rebuilds():
    async def body(table, pilot):
        _sync_rows(table, _rows(("1", "a"), ("2", "b")))
        await pilot.pause()
        rebuilt = _sync_rows(table, _rows(("1", "a"), ("2", "b"), ("3", "c")))
        return rebuilt, table.row_count

    rebuilt, count = _run(body)
    assert rebuilt is True
    assert count == 3


def test_reorder_counts_as_a_rebuild():
    """Row order carries meaning (unread first), so a reorder must be applied."""

    async def body(table, pilot):
        _sync_rows(table, _rows(("1", "a"), ("2", "b")))
        await pilot.pause()
        rebuilt = _sync_rows(table, _rows(("2", "b"), ("1", "a")))
        return rebuilt, [str(k.value) for k in table.rows]

    rebuilt, order = _run(body)
    assert rebuilt is True
    assert order == ["2", "1"]


def test_removal_is_applied():
    async def body(table, pilot):
        _sync_rows(table, _rows(("1", "a"), ("2", "b")))
        await pilot.pause()
        _sync_rows(table, _rows(("1", "a")))
        return table.row_count, [str(k.value) for k in table.rows]

    count, order = _run(body)
    assert count == 1
    assert order == ["1"]


def test_empty_target_clears_table():
    async def body(table, pilot):
        _sync_rows(table, _rows(("1", "a")))
        await pilot.pause()
        _sync_rows(table, [])
        return table.row_count

    assert _run(body) == 0
