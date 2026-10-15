import asyncio

import pytest
from textual.widgets import DataTable

from lemonaid import groups
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp

from ..shared import lemons


@pytest.mark.parametrize("size", [(120, 20), (40, 25)])
@pytest.mark.parametrize("change", ["insert", "remove", "resize", "focus", "unchanged", "group"])
def test_refresh_keeps_visible_row(monkeypatch, tmp_path, size, change):
    rows, _ = lemons(monkeypatch, tmp_path, 45)

    async def check():
        app = LemonaidApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            table = app.query_one("#main_table", DataTable)
            table.move_cursor(row=0)
            y = sum(row.height for row in table.ordered_rows[:20]) + 1
            table.scroll_to(y=y, animate=False)
            await pilot.pause()
            anchor = table.ordered_rows[21]
            key = anchor.key

            def top():
                return (
                    sum(row.height for row in table.ordered_rows[: table.get_row_index(key)])
                    - table.scroll_y
                )

            before = top()
            old_scroll = table.scroll_y
            with db.connect() as conn:
                if change == "insert":
                    db.add(
                        conn, "claude:new", "new", "new", {"tty": "/dev/new"}, switch_source="tmux"
                    )
                elif change == "group":
                    groups.store.add(
                        conn,
                        groups.store.create(conn, "Readers"),
                        tuple(row.channel for row in rows[:5]),
                    )
                elif change == "remove":
                    conn.execute("DELETE FROM notifications WHERE id = ?", (rows[2].id,))
                    conn.commit()
                elif change == "resize":
                    conn.execute(
                        "UPDATE notifications SET message = ? WHERE id = ?",
                        ("many words " * 80, rows[2].id),
                    )
                    conn.commit()
            if change == "focus":
                app._attention.focused = frozenset({"/dev/test-44"})
            app._refresh_notifications()
            await pilot.pause()
            assert top() == before
            if change in {"focus", "unchanged"}:
                assert table.scroll_y == old_scroll
            table.move_cursor(row=40)
            await pilot.pause()
            assert table.scroll_y != old_scroll

    asyncio.run(check())
