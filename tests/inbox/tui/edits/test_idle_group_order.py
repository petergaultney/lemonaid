"""Switching focused idle lemons must not reorder the open group."""

import os
from pathlib import Path

import pytest

from lemonaid import groups
from lemonaid.inbox import db
from lemonaid.inbox.tui.live.inbox_list import InboxList

from .shared import channels, keep_sessions, run, session  # noqa: F401


@pytest.mark.parametrize("size", [(120, 40), (44, 60)])
def test_switching_between_idle_lemons_keeps_their_group_order(size):
    Path(os.environ["LEMONAID_CONFIG"]).write_text('[tui]\nfold_statuses = ["idle"]\n')
    with db.connect() as conn:
        group = groups.store.create(conn, "Work")
        groups.store.add(conn, group, [session(conn, name, "") for name in ("older", "newer")])
        ttys = {n.channel: n.metadata["tty"] for n in db.get_active(conn)}

    async def steps(app, pilot):
        app.query_one(InboxList).fold_open = True
        for name in ("older", "newer", "older"):
            app._attention.note(ttys[f"claude:{name}"])
            app._refresh_notifications()
            await pilot.pause()
            assert channels(app) == ["", "claude:newer", "claude:older"]

    run(steps, size=size)
