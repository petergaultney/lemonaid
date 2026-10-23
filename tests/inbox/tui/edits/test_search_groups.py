"""A search draws matches under their groups and counts each lemon once."""

import os
from pathlib import Path

import pytest
from textual.widgets import Static

from lemonaid import groups
from lemonaid.inbox import db

from .shared import channels, keep_sessions, run, session  # noqa: F401


def test_a_lemon_in_two_groups_is_one_search_match():
    with db.connect() as conn:
        lemon = session(conn, "needle", "")
        session(conn, "other", "")
        for name in ("A", "B"):
            groups.store.add(conn, groups.store.create(conn, name), [lemon])

    async def steps(app, pilot):
        await pilot.press("/", "n", "e", "e", "d", "l", "e")
        await pilot.pause()
        assert channels(app) == ["", "claude:needle", "", "claude:needle"]
        assert "1 inbox match" in str(app.query_one("#status", Static).content)

    run(steps)


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("size", [(120, 40), (44, 60)])
def test_search_keeps_headings_and_configured_ungrouped_position(enabled, size):
    Path(os.environ["LEMONAID_CONFIG"]).write_text(
        f'[inbox]\nungrouped_first = {str(enabled).lower()}\n[tui]\nfold_statuses = ["idle"]\n'
    )
    with db.connect() as conn:
        member = session(conn, "needle-member", "")
        group = groups.store.create(conn, "Work")
        groups.store.add(conn, group, [member])
        groups.arrangement.set_collapsed(conn, group, True)
        session(conn, "needle-loose", "")
        session(conn, "unmatched", "blocked")

    async def steps(app, pilot):
        await pilot.press("/", *"needle")
        await pilot.pause()
        assert channels(app) == (
            ["claude:needle-loose", "", "claude:needle-member"]
            if enabled
            else ["", "claude:needle-member", "claude:needle-loose"]
        )
        assert "2 inbox matches" in str(app.query_one("#status", Static).content)

    run(steps, size=size)
