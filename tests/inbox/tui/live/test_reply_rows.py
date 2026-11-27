"""A row a tool keeps for a lemon is drawn right under that lemon, in its group, whatever terminal the
inbox is in, and only where the lemon's own row is drawn."""

import asyncio

import pytest
from textual.widgets import DataTable

from lemonaid.brief import attached, identity, store
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.watchers import watcher_hooks

from . import shared


def _session(name: str, *, source: str = "tmux", hidden: bool = False) -> db.Notification:
    with db.connect() as conn:
        row = db.add(conn, f"claude:{name}", "working", name, {"cwd": "/tmp"})
        conn.execute(
            "UPDATE notifications SET switch_source = ?, status = 'read' WHERE id = ?",
            (source, row.id),
        )
        conn.commit()
        path = store.briefs_dir() / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        hide = "Hidden: yes\n" if hidden else ""
        path.write_text(f"# {name}\n\nBrief-ID: {name}.SampleBin\n{hide}\n## Goal\n\nWork.\n")
        identity.ensure(conn, path)
        attached.attach(conn, row.channel, path)
        return row


@pytest.fixture(autouse=True)
def _keep_sessions(monkeypatch):
    monkeypatch.setattr(watcher_hooks, "archive_channel", lambda channel, why: None)


def _table_lines(app) -> list[str]:
    table = app.query_one("#main_table", DataTable)
    return [" ".join(str(cell) for cell in table.get_row_at(i)) for i in range(table.row_count)]


def test_a_reply_row_is_drawn_under_its_lemon(tmp_path, monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/tmux-1/default,1,0")
    _session("alpha")
    _session("beta")
    _session("elsewhere", source="wezterm")
    doc = tmp_path / "guide.md"
    doc.write_text("# Guide\n")
    shared.add_item(doc, "claude:alpha", "↳ 💬 guide.md · 2 unread")
    shared.add_item(doc, "claude:elsewhere", "from afar")
    lines: list[str] = []

    async def run() -> None:
        app = LemonaidApp()
        async with app.run_test(size=(160, 30)) as pilot:
            await pilot.pause()
            lines.extend(_table_lines(app))

    asyncio.run(run())

    reply_at = next(i for i, line in enumerate(lines) if "guide.md" in line)
    assert "↳ 💬 guide.md · 2 unread" in lines[reply_at], lines
    assert "alpha" in lines[reply_at - 1], lines
    assert "item" not in lines[reply_at], lines  # no model label of its own
    assert not any("from afar" in line for line in lines), lines


def test_enter_on_a_reply_row_in_the_other_pane_opens_it(tmp_path, monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/tmux-1/default,1,0")
    _session("here")
    _session("there", source="wezterm")
    doc = tmp_path / "guide.md"
    doc.write_text("# Guide\n")
    shared.add_item(doc, "claude:there")
    opened: list[str] = []
    monkeypatch.setattr(
        LemonaidApp, "_switch_to_notification", lambda self, n, **kw: opened.append(n.channel)
    )

    async def run() -> None:
        app = LemonaidApp()
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            other = app.query_one("#other_sources_table", DataTable)
            rows = [" ".join(str(c) for c in other.get_row_at(i)) for i in range(other.row_count)]
            other.focus()
            for target in ("there", "guide.md"):
                at = next(i for i, line in enumerate(rows) if target in line)
                other.move_cursor(row=at)
                await pilot.press("enter")
                await pilot.pause()

    asyncio.run(run())

    assert opened == [shared.item_channel(doc, "claude:there")]


def test_an_unread_reply_brings_back_its_hidden_lemon_in_the_other_pane(tmp_path):
    import time

    from lemonaid.config import load_config
    from lemonaid.inbox import presence
    from lemonaid.inbox.tui.live import inbox_frame
    from lemonaid.inbox.tui.rows import brief_cards, pr_numbers
    from lemonaid.stalls import inbox as stalls_inbox

    _session("there", source="wezterm", hidden=True)
    _session("quiet", source="wezterm", hidden=True)  # hidden, and nothing to bring it back
    doc = tmp_path / "guide.md"
    doc.write_text("# Guide\n")
    shared.add_item(doc, "claude:there")

    with db.connect() as conn:
        frame = inbox_frame.load(
            conn,
            load_config(),
            brief_cards.BriefCache(),
            presence.Probe(),
            pr_numbers.Cache(),
            stalls_inbox.Tracker(),
            env_filter="tmux",
            focused=frozenset(),
            search_text=None,
            current_key=None,
            other_key=None,
            unfolded_ids=set(),
            shared_names=set(),
            now=time.time(),
        )

    assert [n.channel for n in frame.other] == [
        "claude:there",
        shared.item_channel(doc, "claude:there"),
    ]
