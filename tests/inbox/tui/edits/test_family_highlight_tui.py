import os
from pathlib import Path

import pytest
from rich.console import Console
from textual.widgets import DataTable

from lemonaid import groups
from lemonaid.inbox import db
from lemonaid.inbox.tui.live.inbox_list import InboxList
from lemonaid.lineage import links

from .shared import keep_sessions, run, session  # noqa: F401


def _row(table, name):
    return next(
        (str(key.value), cell)
        for key in table.rows
        for cell in table.get_row(key)
        if name in cell.plain
    )


def _relation(text, arrow):
    console = Console()
    return any(
        character == arrow
        and (style := text.get_style_at_offset(console, i)).bold
        and not style.dim
        for i, character in enumerate(text.plain)
    )


def _move(table, name):
    table.move_cursor(row=table.get_row_index(_row(table, name)[0]))


@pytest.mark.parametrize("size", [(120, 40), (44, 60), (28, 60)])
def test_cursor_marks_relatives_without_refresh_or_rebuild(size, monkeypatch):
    Path(os.environ["LEMONAID_CONFIG"]).write_text(
        "[tui]\nbrief_status = true\nrefresh_interval = 600\n"
    )
    with db.connect() as conn:
        parent = session(conn, "parent", "")
        child = session(conn, "child", "")
        sibling = session(conn, "sibling", "")
        grandchild = session(conn, "grandkid", "")
        unrelated = session(conn, "unrelated", "")
        links.set_parent(conn, child, parent)
        links.set_parent(conn, sibling, parent)
        links.set_parent(conn, grandchild, child)
        groups.store.add(conn, groups.store.create(conn, "Work"), [parent, child, unrelated])
        groups.store.add(conn, groups.store.create(conn, "Other"), [child, sibling, grandchild])

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        changed = []
        original_update = table.update_cell_at

        def update(coordinate, *args, **kwargs):
            changed.append(str(table.ordered_rows[coordinate[0]].key.value))
            return original_update(coordinate, *args, **kwargs)

        def unexpected(*args, **kwargs):
            raise AssertionError("cursor movement must not reload or rebuild the inbox")

        monkeypatch.setattr(table, "update_cell_at", update)
        monkeypatch.setattr(table, "clear", unexpected)
        monkeypatch.setattr(app, "_activate_row", unexpected)
        monkeypatch.setattr(app.query_one(InboxList), "refresh_list", unexpected)
        positions = {
            name: _row(table, name)[1].plain.index(name) for name in ("parent", "child", "sibling")
        }
        _move(table, "parent")
        await pilot.pause()
        assert _relation(_row(table, "child")[1], "\u2191")
        assert _relation(_row(table, "sibling")[1], "\u2191")
        assert not _relation(_row(table, "grandkid")[1], "\u2191")
        assert (
            len(
                [
                    key
                    for key in table.rows
                    if any(_relation(c, "\u2191") for c in table.get_row(key))
                ]
            )
            == 3
        )
        assert _row(table, "unrelated")[0] not in changed
        _move(table, "child")
        await pilot.pause()
        assert _relation(_row(table, "parent")[1], "\u2193")
        assert _relation(_row(table, "grandkid")[1], "\u2191")
        assert not _relation(_row(table, "sibling")[1], "\u2191")
        for name, position in positions.items():
            assert _row(table, name)[1].plain.index(name) == position
        _move(table, "unrelated")
        await pilot.pause()
        assert not any(
            _relation(cell, "\u2191") or _relation(cell, "\u2193")
            for key in table.rows
            for cell in table.get_row(key)
        )

    run(steps, size)


@pytest.mark.parametrize("size", [(120, 40), (44, 60)])
def test_highlight_tracks_relatives_across_the_two_inbox_tables(size, monkeypatch):
    monkeypatch.setattr("lemonaid.inbox.tui.app.detect_terminal_switch_source", lambda: "tmux")
    monkeypatch.setattr("lemonaid.handlers._resolve_pane_from_tty", lambda tty: (None, None))
    with db.connect() as conn:
        parent = session(conn, "parent", "blocked")
        child = session(conn, "child", "alert")
        links.set_parent(conn, child, parent)
        conn.execute(
            "UPDATE notifications SET switch_source = 'wezterm' WHERE channel = 'claude:child'"
        )
        conn.commit()

    async def steps(app, pilot):
        main = app.query_one("#main_table", DataTable)
        other = app.query_one("#other_sources_table", DataTable)
        assert "\u21931" in _row(main, "parent")[1].plain
        main.focus()
        _move(main, "parent")
        await pilot.pause()
        assert _relation(_row(other, "child")[1], "\u2191")
        other.focus()
        await pilot.pause()
        assert _relation(_row(main, "parent")[1], "\u2193")
        assert not _relation(_row(other, "child")[1], "\u2191")
        app._refresh_notifications()
        await pilot.pause()
        assert _relation(_row(main, "parent")[1], "\u2193")

    run(steps, size)


@pytest.mark.parametrize("size", [(120, 40), (44, 60)])
def test_relationship_marks_survive_refresh_folding_and_search(size):
    Path(os.environ["LEMONAID_CONFIG"]).write_text('[tui]\nfold_statuses = ["idle"]\n')
    with db.connect() as conn:
        parent = session(conn, "parent", "blocked")
        child = session(conn, "child", "")
        links.set_parent(conn, child, parent)
        groups.store.add(conn, groups.store.create(conn, "Work"), [parent, child])

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)
        _move(table, "parent")
        await pilot.pause()
        assert "\u21930/1" in _row(table, "parent")[1].plain
        await pilot.press("w")
        await pilot.pause()
        assert _relation(_row(table, "child")[1], "\u2191")
        app._refresh_notifications()
        await pilot.pause()
        assert _relation(_row(table, "child")[1], "\u2191")
        app._content.searching = True
        app._content.filter_text = "parent"
        app._refresh_notifications()
        await pilot.pause()
        assert "\u21930/1" in _row(table, "parent")[1].plain
        assert not any(_relation(c, "\u2191") for key in table.rows for c in table.get_row(key))
        app._content.searching = False
        app._content.filter_text = ""
        app._refresh_notifications()
        await pilot.pause()
        assert _relation(_row(table, "child")[1], "\u2191")
        table.move_cursor(row=0)
        await pilot.pause()
        assert not _relation(_row(table, "child")[1], "\u2191")

    run(steps, size)
