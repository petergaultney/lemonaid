"""`[tui] brief_names_in_inbox` shows each brief name after its session name."""

import asyncio

from textual.widgets import DataTable

from lemonaid.brief import attached, identity, store
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import _SIDEBAR_COLS, LemonaidApp


def _lemon_with_a_brief() -> str:
    path = store.briefs_dir() / "hq.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# hq\n\nLemon-ID: plan-manager.BlessBar\n\nStatus: working\n")
    with db.connect() as conn:
        n = db.add(conn, "claude:hq", "a message", "lemonaid HQ", {"tty": "/dev/ttys901"})
        conn.execute("UPDATE notifications SET switch_source = 'tmux' WHERE id = ?", (n.id,))
        conn.commit()
        attached.attach(conn, "claude:hq", path)
        return identity.ensure(conn, path)


def _first_row(width: int, wordybin: bool) -> str:
    async def run() -> str:
        app = LemonaidApp()
        app.config.tui.brief_names_in_inbox = wordybin
        async with app.run_test(size=(width, 30)) as pilot:
            await pilot.pause()
            await pilot.pause()
            table = app.query_one("#main_table", DataTable)
            return " ".join(str(cell) for cell in table.get_row_at(0))

    return asyncio.run(run())


def test_the_wide_table_shows_the_wordybin_after_the_name_only_when_asked():
    _lemon_with_a_brief()

    assert "lemonaid HQ · BlessBar" in _first_row(160, True)
    assert "BlessBar" not in _first_row(160, False)


def test_a_sidebar_card_shows_the_wordybin_after_the_name():
    _lemon_with_a_brief()

    assert "lemonaid HQ · BlessBar" in _first_row(_SIDEBAR_COLS - 4, True)
