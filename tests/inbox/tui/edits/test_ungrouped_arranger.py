"""Group placement preserves the arranger's order within each block."""

import os
import time
from pathlib import Path

import pytest

from lemonaid import groups
from lemonaid.inbox import db, pins
from lemonaid.inbox.tui.live.inbox_list import InboxList
from tests.inbox.tui.live.test_arrange_tui import _serve

from .shared import channels, keep_sessions, run, session  # noqa: F401


@pytest.mark.parametrize("enabled", [True, False])
def test_arranger_member_and_ungrouped_order(tmp_path, enabled):
    with db.connect() as conn:
        group = groups.store.create(conn, "Work")
        groups.store.add(conn, group, [session(conn, name, "blocked") for name in ("a", "b")])
        session(conn, "loose-a", "blocked")
        session(conn, "loose-b", "blocked")
    command = _serve(
        tmp_path,
        "def arrange(snapshot):\n"
        '    rows = sorted(snapshot["rows"], key=lambda row: row["name"])\n'
        '    return {"rows": [row["id"] for row in rows], "fold_label": "arranged"}\n',
    )
    Path(os.environ["LEMONAID_CONFIG"]).write_text(
        f"[inbox]\narrange = {command!r}\nungrouped_first = {str(enabled).lower()}\n"
    )

    async def steps(app, pilot):
        deadline = time.monotonic() + 5
        while app.query_one(InboxList).fold_name != "arranged":
            assert time.monotonic() < deadline
            await pilot.pause()
        grouped = ["", "claude:a", "claude:b"]
        loose = ["claude:loose-a", "claude:loose-b"]
        assert channels(app) == ([*loose, *grouped] if enabled else [*grouped, *loose])

    run(steps)


@pytest.mark.parametrize("size", [(120, 40), (44, 60)])
@pytest.mark.parametrize("enabled", [True, False])
def test_open_fold_restores_arranger_folded_pin(tmp_path, enabled, size):
    with db.connect() as conn:
        group = groups.store.create(conn, "Work")
        groups.store.add(conn, group, [session(conn, "member", "blocked")])
        session(conn, "loose", "blocked")
        session(conn, "pin", "")
        pins.pin(conn, "claude:pin")
    command = _serve(
        tmp_path,
        "def arrange(snapshot):\n"
        '    rows = snapshot["rows"]\n'
        '    return {"rows": [r["id"] for r in rows if not r["pinned"]], '
        '"folded": [r["id"] for r in rows if r["pinned"]], "fold_label": "arranged"}\n',
    )
    Path(os.environ["LEMONAID_CONFIG"]).write_text(
        f"[inbox]\narrange = {command!r}\nungrouped_first = {str(enabled).lower()}\n"
    )

    async def steps(app, pilot):
        deadline = time.monotonic() + 5
        while app.query_one(InboxList).fold_name != "arranged":
            assert time.monotonic() < deadline
            await pilot.pause()
        grouped = ["", "claude:member"]
        loose = ["claude:loose"]
        expected = [*loose, *grouped] if enabled else [*grouped, *loose]
        assert channels(app) == expected
        await pilot.press(app.config.tui.keybindings.fold)
        await pilot.pause()
        assert channels(app) == ["claude:pin", *expected]
        await pilot.press(app.config.tui.keybindings.fold)
        await pilot.pause()
        assert channels(app) == expected

    run(steps, size=size)
