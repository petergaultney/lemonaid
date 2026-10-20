import os
from pathlib import Path

import pytest
from rich.cells import cell_len
from rich.console import Console
from textual.widgets import DataTable

from lemonaid import groups
from lemonaid.inbox import db, emoji, pins
from lemonaid.inbox.tui.utils import PIN_MARK
from lemonaid.lineage import links

from .shared import channels, keep_sessions, run, session  # noqa: F401


@pytest.mark.parametrize("size", [(120, 40), (44, 60)])
@pytest.mark.parametrize("shared_group", [True, False])
def test_parent_marker_counts_children_across_groups(size, shared_group):
    Path(os.environ["LEMONAID_CONFIG"]).write_text("[tui]\nbrief_status = true\n")
    with db.connect() as conn:
        parent = session(conn, "parent", "blocked")
        child = session(conn, "child", "alert")
        sibling = session(conn, "sibling", "alert")
        links.set_parent(conn, child, parent)
        links.set_parent(conn, sibling, parent)
        group = groups.store.create(conn, "Work")
        groups.store.add(conn, group, [parent, child] if shared_group else [parent])
        other = groups.store.create(conn, "Other")
        groups.store.add(conn, other, [parent, sibling, *([] if shared_group else [child])])

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        parents = []
        for key in table.rows:
            cells = table.get_row(key)
            cell = next((c for c in cells if "parent" in c.plain), None)
            if cell is not None:
                count = 2
                assert "\u21932" in cell.plain
                assert "parent \u2193" not in cell.plain
                assert ("\u2193" in cell.plain) == bool(count)
                if count:
                    assert cell.get_style_at_offset(Console(), cell.plain.index("\u2193")).dim
                parents.append(cell.plain)
        assert len(parents) == 2

    run(steps, size)


@pytest.mark.parametrize("size", [(120, 40), (44, 60)])
def test_parent_marker_updates_as_children_are_folded_and_restored(size):
    Path(os.environ["LEMONAID_CONFIG"]).write_text(
        '[tui]\nbrief_status = true\nfold_statuses = ["idle"]\n'
    )
    with db.connect() as conn:
        parent = session(conn, "parent", "blocked")
        child = session(conn, "child", "")
        links.set_parent(conn, child, parent)
        group = groups.store.create(conn, "Work")
        groups.store.add(conn, group, [parent, child])

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)

        def parent_text():
            return next(
                cell.plain
                for key in table.rows
                for cell in table.get_row(key)
                if "parent" in cell.plain
            )

        assert "\u21930/1" in parent_text()
        await pilot.press("w")
        await pilot.pause()
        assert "\u21931" in parent_text()
        await pilot.press("w")
        await pilot.pause()
        assert "\u21930/1" in parent_text()

    run(steps, size)


@pytest.mark.parametrize("size", [(120, 40), (44, 60), (28, 60)])
@pytest.mark.parametrize("decoration", ["", "\U0001f9ed"])
def test_parent_marker_stays_with_emoji_and_pin_when_names_are_truncated(size, decoration):
    with db.connect() as conn:
        parent = session(conn, "parent" + "x" * 70, "blocked")
        child = session(conn, "child" + "x" * 70, "alert")
        links.set_parent(conn, child, parent)
        groups.store.add(conn, groups.store.create(conn, "Work"), [parent, child])
        parent_channel = "claude:parent" + "x" * 70
        emoji.set_emoji(conn, parent_channel, decoration)
        emoji.set_emoji(conn, "claude:child" + "x" * 70, decoration)
        pins.pin(conn, parent_channel)

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        rows = [table.get_row(key) for key in table.rows]
        parent = next(cell for row in rows for cell in row if "parent" in cell.plain)
        child = next(cell for row in rows for cell in row if "child" in cell.plain)
        assert "\u2193" not in child.plain
        assert parent.plain.index("parent") == child.plain.index("child")
        if size[0] < 54:
            lines = parent.plain.splitlines()
            assert "\u2193" not in lines[0]
            assert "\u21931" in lines[1]
            assert (
                f"\u21931 {decoration} {PIN_MARK}" if decoration else f"\u21931 {PIN_MARK}"
            ) in lines[1]
            assert all(cell_len(line) <= size[0] for line in lines)
        else:
            prefix = parent.plain.split(decoration if decoration else "parent", 1)[0]
            assert prefix.rstrip().endswith("\u21931")
            assert parent.plain.index("\u2193") < parent.plain.index("parent")

    run(steps, size)
