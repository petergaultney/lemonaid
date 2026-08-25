"""Clicking a row switches to it, rather than only moving the cursor.

Since Textual 7.5.0 the base DataTable posts RowSelected only for a click on the
coordinate the cursor already holds, so with a row cursor and several columns the
first click on a row only highlights it and the second selects. The inbox's rows
are destinations, so the first click is the whole intent.
"""

import asyncio

from textual.app import App, ComposeResult
from textual.widgets import DataTable

from lemonaid.inbox.tui.table import ClickToActTable


class _Harness(App):
    def __init__(self) -> None:
        super().__init__()
        self.selected: list[int] = []
        self.highlighted: list[int] = []

    def compose(self) -> ComposeResult:
        yield ClickToActTable(id="t")

    def on_mount(self) -> None:
        table = self.query_one("#t", ClickToActTable)
        table.cursor_type = "row"
        table.focus()
        for column in ("a", "b", "c"):
            table.add_column(column, width=10)
        for name in ("one", "two", "three"):
            table.add_row(name, name, name)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.selected.append(event.cursor_row)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.highlighted.append(event.cursor_row)


def _run(*spots: tuple[int, int], keys: tuple[str, ...] = ()) -> tuple[list[int], list[int]]:
    """Click each (x, row), then press `keys`; return (selected, highlighted)."""

    async def go() -> tuple[list[int], list[int]]:
        app = _Harness()
        async with app.run_test(size=(50, 12)) as pilot:
            await pilot.pause()
            app.selected.clear()
            app.highlighted.clear()
            for x, row in spots:
                await pilot.click("#t", offset=(x, 1 + row))
                await pilot.pause()
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            return app.selected, app.highlighted

    return asyncio.run(go())


def test_one_click_on_a_far_column_selects_that_row():
    """The reported case: a row cursor makes the column invisible to the user."""
    selected, _ = _run((25, 2))

    assert selected == [2]


def test_a_click_selects_once_not_twice():
    """The base posts for a click already on the cursor; posting again double-fires."""
    selected, _ = _run((2, 0))

    assert selected == [0]


def test_each_click_selects_the_row_it_landed_on():
    selected, _ = _run((25, 2), (2, 0), (14, 1))

    assert selected == [2, 0, 1]


def test_arrow_keys_move_without_selecting():
    """Keyboard navigation still browses; Enter is what commits."""
    selected, highlighted = _run(keys=("down", "down", "up"))

    assert selected == []
    assert highlighted == [1, 2, 1]


def test_enter_still_selects():
    selected, _ = _run(keys=("down", "enter"))

    assert selected == [1]
