"""Header counts include hidden current members and exclude archived history."""

import pytest
from textual.widgets import DataTable

from lemonaid import brief, groups
from lemonaid.inbox import db

from .shared import keep_sessions, run, session  # noqa: F401


@pytest.mark.parametrize("size", [(44, 60), (120, 40)])
def test_header_counts_current_members_and_actual_visible_rows(size):
    with db.connect() as conn:
        group = groups.store.create(conn, "Work")
        lead = session(conn, "lead", "working")
        worker = session(conn, "worker", "working")
        reviewer = session(conn, "review-quiet", "working")
        path = brief.store.briefs_dir() / "review-quiet.md"
        path.write_text(path.read_text() + f"\nParent: {worker}\n")
        archived = session(conn, "old", "working")
        groups.store.add(conn, group, [lead, worker, reviewer, archived])
        db.archive_channel(conn, "claude:old", reason="test")

    def header(table):
        return next(cell.plain for cell in table.get_row_at(0) if cell.plain)

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        expanded = header(table)
        table.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        collapsed = header(table)
        await pilot.press("enter")
        await pilot.pause()
        return expanded, collapsed, header(table)

    expanded, collapsed, reopened = run(steps, size=size)

    assert "(2/3)" in expanded
    assert "(0/3)" in collapsed
    assert "(2/3)" in reopened
