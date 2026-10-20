"""Opening the fold keeps ungrouped lemons in their configured position."""

import os
import time
from pathlib import Path

import pytest

from lemonaid import groups
from lemonaid.inbox import db, pins
from lemonaid.inbox.tui import app as app_mod
from lemonaid.inbox.tui.live.inbox_list import InboxList
from tests.inbox.tui.live.test_arrange_tui import _serve

from .shared import channels, keep_sessions, run, session  # noqa: F401


@pytest.mark.parametrize("size", [(120, 40), (44, 60)])
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("arranged", [True, False])
def test_focus_keeps_open_fold_ungrouped_order(tmp_path, monkeypatch, size, enabled, arranged):
    command = (
        _serve(
            tmp_path,
            "def arrange(snapshot):\n"
            '    rows = sorted(snapshot["rows"], key=lambda row: -row["id"])\n'
            '    folded = [row["id"] for row in rows if not row["pinned"] and not row["brief"]["status"]]\n'
            '    return {"rows": [row["id"] for row in rows if row["id"] not in folded], "folded": folded, "fold_label": "quiet"}\n',
        )
        if arranged
        else ""
    )
    Path(os.environ["LEMONAID_CONFIG"]).write_text(
        f"[inbox]\nungrouped_first = {str(enabled).lower()}\narrange = {command!r}\n"
        '[tui]\nfold_statuses = ["idle"]\n'
    )
    focused: set[str] = set()
    monkeypatch.setattr(app_mod.navigation, "focused_ttys", lambda socket=None: focused)
    monkeypatch.setattr("lemonaid.inbox.tui.watchers.focus.FOCUS_CACHE_SECONDS", 0.0)
    with db.connect() as conn:
        group = groups.store.create(conn, "Work")
        groups.store.add(conn, group, [session(conn, "member", "blocked")])
        session(conn, "older", "")
        session(conn, "newer", "")
        session(conn, "hq", "")
        pins.pin(conn, "claude:hq")
        tty = next(n.metadata["tty"] for n in db.get_active(conn) if n.channel == "claude:older")

    async def steps(app, pilot):
        if arranged:
            deadline = time.monotonic() + 5
            while app.query_one(InboxList).fold_name != "quiet":
                assert time.monotonic() < deadline
                await pilot.pause()
        assert channels(app) == ["claude:hq", "", "claude:member"]
        await pilot.press(app.config.tui.keybindings.fold)
        await pilot.pause()
        assert app.query_one(InboxList).fold_open
        loose = ["claude:newer", "claude:older"]
        grouped = ["", "claude:member"]
        expected = ["claude:hq", *(loose + grouped if enabled else grouped + loose)]
        assert channels(app) == expected
        focused.add(tty)
        app._refresh_notifications()
        await pilot.pause()
        assert channels(app) == expected
        focused.clear()
        app._select_channel("claude:hq")
        app._refresh_notifications()
        await pilot.pause()
        assert channels(app) == expected

    run(steps, size=size)
