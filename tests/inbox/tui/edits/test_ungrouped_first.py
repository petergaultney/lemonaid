"""Ungrouped rows stay visible above groups, with an opt-out to the former order."""

import os
from pathlib import Path

import pytest
from textual.widgets import DataTable

from lemonaid import groups
from lemonaid.inbox import db, pins
from lemonaid.inbox.tui.live.inbox_list import InboxList

from .shared import channels, keep_sessions, run, session  # noqa: F401


@pytest.mark.parametrize("size", [(120, 40), (44, 60)])
@pytest.mark.parametrize("enabled", [None, True, False])
def test_ungrouped_order_and_cursor(size, enabled):
    if enabled is not None:
        Path(os.environ["LEMONAID_CONFIG"]).write_text(
            f"[inbox]\nungrouped_first = {str(enabled).lower()}\n"
        )
    with db.connect() as conn:
        group = groups.store.create(conn, "Work")
        groups.store.add(conn, group, [session(conn, "member", "blocked")])
        session(conn, "loose", "blocked")

    async def steps(app, pilot):
        expected = (
            ["", "claude:member", "claude:loose"]
            if enabled is False
            else ["claude:loose", "", "claude:member"]
        )
        assert channels(app) == expected
        table = app.query_one("#main_table", DataTable)
        assert table.cursor_coordinate.row == 0
        table.move_cursor(row=expected.index("claude:loose"))
        await pilot.pause()
        app._refresh_notifications()
        await pilot.pause()
        assert channels(app)[table.cursor_coordinate.row] == "claude:loose"
        with db.connect() as conn:
            session(conn, "pin", "active")
            pins.pin(conn, "claude:pin")
        app._refresh_notifications()
        await pilot.pause()
        assert channels(app) == ["claude:pin", *expected]
        assert channels(app)[table.cursor_coordinate.row] == "claude:loose"

    run(steps, size=size)


@pytest.mark.parametrize("enabled", [True, False])
def test_fold_expand_keeps_grouped_rows_in_place(enabled):
    Path(os.environ["LEMONAID_CONFIG"]).write_text(
        f"[inbox]\nungrouped_first = {str(enabled).lower()}\n" '[tui]\nfold_statuses = ["idle"]\n'
    )
    with db.connect() as conn:
        group = groups.store.create(conn, "Work")
        groups.store.add(conn, group, [session(conn, "member", "")])
        session(conn, "loose", "blocked")
        session(conn, "folded", "")

    async def steps(app, pilot):
        assert channels(app) == ["claude:loose"]
        await pilot.press(app.config.tui.keybindings.fold)
        await pilot.pause()
        expected = (
            ["claude:loose", "claude:folded", "", "claude:member"]
            if enabled
            else ["", "claude:member", "claude:loose", "claude:folded"]
        )
        assert app.query_one(InboxList).fold_open
        assert channels(app) == expected

    run(steps)
