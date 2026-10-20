import os
import time
from pathlib import Path

import pytest
from textual.widgets import DataTable

from lemonaid import groups
from lemonaid.brief import store
from lemonaid.inbox import db
from lemonaid.lineage import links

from .shared import keep_sessions, run, session  # noqa: F401


@pytest.mark.parametrize("size", [(120, 40), (44, 60)])
def test_total_includes_quiet_and_other_group_children_but_excludes_retired_sessions(size):
    Path(os.environ["LEMONAID_CONFIG"]).write_text('[tui]\nfold_statuses = ["idle"]\n')
    with db.connect() as conn:
        parent = session(conn, "parent", "blocked")
        children = {
            name: session(conn, name, "alert" if name == "shown" else "")
            for name in ("shown", "hidden", "folded", "elsewhere", "retired", "snoozed")
        }
        for child in children.values():
            links.set_parent(conn, child, parent)
        session(conn, "grandchild", "")
        links.set_parent(conn, session(conn, "unrelated", ""), children["shown"])
        hidden = store.briefs_dir() / "hidden.md"
        hidden.write_text(hidden.read_text().replace("# hidden", "# hidden\n\nHidden: yes"))
        db.archive_channel(conn, "claude:retired", "test")
        db.snooze(
            conn,
            db.get_by_channel(conn, "claude:snoozed", unread_only=False).id,
            time.time() + 3600,
        )
        groups.store.add(
            conn, groups.store.create(conn, "Work"), [parent, children["shown"], children["folded"]]
        )
        other = groups.store.create(conn, "Other")
        groups.store.add(conn, other, [children["elsewhere"], children["shown"]])
        groups.arrangement.set_collapsed(conn, other, True)

    async def steps(app, pilot):
        table = app.query_one("#main_table", DataTable)

        def parent_text():
            return next(
                c.plain for key in table.rows for c in table.get_row(key) if "parent" in c.plain
            )

        assert "\u21931/4" in parent_text()
        await pilot.press("w")
        await pilot.pause()
        assert "\u21933/4" in parent_text()
        app._content.searching = True
        app._content.filter_text = "parent"
        app._refresh_notifications()
        await pilot.pause()
        assert "\u21930/4" in parent_text()

    run(steps, size)
