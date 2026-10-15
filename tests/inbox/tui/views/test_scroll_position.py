import asyncio
import time

import pytest
from textual.widgets import DataTable

from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.views import usage_view
from lemonaid.usage import samples

from ..shared import lemons


@pytest.mark.parametrize("mode", ["history", "snoozed", "other", "usage"])
def test_view_refill_keeps_visible_row(monkeypatch, tmp_path, mode):
    rows, _ = lemons(monkeypatch, tmp_path, 45)
    current = {
        f"window-{i:02}": samples.Sample(50, int(time.time()) + 3600, 120) for i in range(45)
    }
    monkeypatch.setattr(usage_view, "read_samples", lambda: current)
    with db.connect() as conn:
        for row in rows[:40]:
            if mode == "history":
                db.archive(conn, row.id)
            elif mode == "snoozed":
                db.snooze(conn, row.id, time.time() + 3600)
            elif mode == "other":
                conn.execute(
                    "UPDATE notifications SET switch_source = ? WHERE id = ?", ("cmux", row.id)
                )
        conn.commit()

    async def check():
        app = LemonaidApp()
        async with app.run_test(size=(120, 30)) as pilot:
            if mode == "history":
                app._set_history_mode(True)
                refresh = app._refresh_history
                table_id = "history"
            elif mode == "snoozed":
                app.action_toggle_snoozed()
                refresh = app._refresh_snoozed
                table_id = "snoozed"
            elif mode == "usage":
                app.action_toggle_usage()
                refresh = app._refresh_usage
                table_id = "usage"
            else:
                refresh = app._refresh_notifications
                table_id = "other_sources"
            await pilot.pause()
            table = app.query_one(f"#{table_id}_table", DataTable)
            assert table.row_count >= 35
            table.move_cursor(row=0)
            table.scroll_to(y=8, animate=False)
            await pilot.pause()
            before = table.scroll_y
            key = table.ordered_rows[9].key
            refresh()
            await pilot.pause()
            assert table.scroll_y == before
            if mode == "usage":
                del current["window-00"]
            else:
                with db.connect() as conn:
                    conn.execute("DELETE FROM notifications WHERE id = ?", (rows[0].id,))
                    conn.commit()
            refresh()
            await pilot.pause()
            assert (
                sum(row.height for row in table.ordered_rows[: table.get_row_index(key)])
                - table.scroll_y
                == 1
            )

    asyncio.run(check())
