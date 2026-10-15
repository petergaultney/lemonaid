import asyncio

import pytest
from textual.app import App

from lemonaid.inbox.tui.tables.scroll_position import StableTable


@pytest.mark.parametrize("change", ["rebuild", "height", "cursor", "deleted", "horizontal"])
def test_table_refresh_preserves_viewport(change):
    async def check():
        app = App()
        async with app.run_test(size=(40, 15)) as pilot:
            table = StableTable()
            await app.mount(table)
            table.add_column("Text", width=90)
            table.cursor_type = "row"
            for i in range(50):
                table.add_row(f"Row {i}", key=str(i), height=3)
            await pilot.pause()
            table.move_cursor(row=0)
            table.scroll_to(x=10, y=61, animate=False)
            await pilot.pause()
            before = table.scroll_y
            with table.preserve_scroll():
                if change in {"rebuild", "deleted"}:
                    table.clear()
                    for i in range(-1, 50):
                        if change == "deleted" and i == 20:
                            continue
                        table.add_row(f"Row {i}", key=str(i), height=3)
                elif change == "height":
                    table.rows[table.ordered_rows[2].key].height = 7
                    table._update_dimensions(table.rows.keys())
            table.move_cursor(row=40, scroll=False)
            await pilot.pause()
            assert table.scroll_x == 10
            expected = before + (
                3 if change in {"rebuild", "deleted"} else 4 if change == "height" else 0
            )
            if change == "deleted":
                expected -= 3
            assert table.scroll_y == expected
            table.move_cursor(row=45)
            await pilot.pause()
            assert table.scroll_y > expected

    asyncio.run(check())


def test_user_scroll_takes_effect_after_refresh():
    async def check():
        app = App()
        async with app.run_test(size=(40, 15)) as pilot:
            table = StableTable()
            await app.mount(table)
            table.add_column("Text")
            for i in range(80):
                table.add_row(str(i), key=str(i))
            await pilot.pause()
            table.scroll_to(y=30, animate=False)
            with table.preserve_scroll():
                table.clear()
                for i in range(80):
                    table.add_row(str(i), key=str(i))
            table.move_cursor(row=70)
            await pilot.pause()
            assert table.scroll_y > 30

    asyncio.run(check())


def test_consecutive_refreshes_preserve_the_visible_row():
    async def check():
        app = App()
        async with app.run_test(size=(40, 15)) as pilot:
            table = StableTable()
            await app.mount(table)
            table.add_column("Text")
            for i in range(80):
                table.add_row(str(i), key=str(i))
            await pilot.pause()
            table.scroll_to(y=30, animate=False)
            for first in [-1, -2]:
                with table.preserve_scroll():
                    table.clear()
                    for i in range(first, 80):
                        table.add_row(str(i), key=str(i))
            await pilot.pause()
            assert table.scroll_y == 32

    asyncio.run(check())
