"""Inbox search and its archive expansion."""

import asyncio

from rich.console import Console
from textual.widgets import DataTable, Input, Static

from lemonaid.brief import attached, identity
from lemonaid.brief import store as brief_store
from lemonaid.inbox import db, search
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.utils import ATTENTION_COLOR


def _add(
    channel: str,
    name: str,
    when: float,
    status: str = "unread",
    switch_source: str = "tmux",
) -> db.Notification:
    with db.connect() as conn:
        return db.add(
            conn,
            channel,
            f"message for {name}",
            name,
            {"cwd": f"/tmp/{name}", "git_branch": name},
            upsert=False,
            switch_source=switch_source,
            created_at=when,
            status=status,
        )


def test_search_matches_active_rows_and_sorts_by_recency():
    older = _add("claude:older", "Alpha", 10)
    newer = _add("claude:newer", "alphabet", 20)
    _add("claude:other", "beta", 30)

    with db.connect() as conn:
        found = search.find(conn, "ALPH", switch_source="tmux")

    assert [(result.notification.id, result.source) for result in found] == [
        (newer.id, "inbox"),
        (older.id, "inbox"),
    ]


def test_archive_expansion_merges_results_and_keeps_active_channel():
    archived = _add("claude:archived", "match archive", 15, "archived")
    live = _add("claude:live", "match old", 10, "read")
    newest = _add("claude:live", "match live", 20)
    _add("claude:snoozed", "match snoozed", 30, "snoozed")

    with db.connect() as conn:
        found = search.find(conn, "match", include_history=True, switch_source="tmux")

    assert [(result.notification.id, result.source) for result in found] == [
        (newest.id, "inbox"),
        (archived.id, "archive"),
    ]
    assert live.id != newest.id


def test_archive_expansion_excludes_live_channels_without_matching_inbox_rows():
    _add("claude:live-one", "old match", 10, "archived")
    _add("claude:live-one", "current", 20)
    _add("claude:live-two", "old match", 11, "archived")
    _add("claude:live-two", "current", 21, "read", "wezterm")
    archived = _add("claude:archived", "old match", 12, "archived")

    with db.connect() as conn:
        found = search.find(conn, "match", include_history=True, switch_source="tmux")

    assert [(result.notification.id, result.source) for result in found] == [
        (archived.id, "archive")
    ]


def test_search_treats_like_metacharacters_as_literal_in_both_sources():
    active = {
        "%": _add("claude:percent", "100%", 20),
        "_": _add("claude:underscore", "under_score", 21),
        "!": _add("claude:bang", "bang!", 22),
    }
    archived = {
        "%": _add("claude:archived-percent", "100%", 10, "archived"),
        "_": _add("claude:archived-underscore", "under_score", 11, "archived"),
        "!": _add("claude:archived-bang", "bang!", 12, "archived"),
    }
    _add("claude:plain", "plain", 23)

    with db.connect() as conn:
        for query in ("%", "_", "!"):
            found = search.find(conn, query, include_history=True, switch_source="tmux")
            assert {result.notification.id for result in found} == {
                active[query].id,
                archived[query].id,
            }
            assert [row.id for row in db.get_history(conn, search=query)] == [archived[query].id]


def test_search_matches_attached_wordybin_names_in_both_sources():
    active = _add("claude:hq", "lemonaid HQ", 20)
    archived = _add("claude:past", "old session", 10, "archived")
    _add("claude:other", "unrelated", 30)
    with db.connect() as conn:
        for channel, name in ((active.channel, "BlessBar"), (archived.channel, "FieldJoy")):
            path = brief_store.briefs_dir() / f"search-{name}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# brief\n\nBrief-ID: search.{name}\n\nStatus: working\n")
            attached.attach(conn, channel, path)
            identity.ensure(conn, path)

        assert [(r.notification.id, r.source) for r in search.find(conn, "blessbar")] == [
            (active.id, "inbox")
        ]
        assert [
            (r.notification.id, r.source)
            for r in search.find(conn, "fieldjoy", include_history=True)
        ] == [(archived.id, "archive")]


def test_search_mode_filters_as_typed_and_shows_archive():
    _add("claude:active", "alpha", 20)
    _add("claude:archive", "alpha archive", 10, "archived")
    _add("claude:other", "beta", 30)

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.press("/")
            await pilot.pause()
            box = app.query_one("#history_filter", Input)
            table = app.query_one("#main_table", DataTable)
            archive = app.query_one("#history_table", DataTable)
            assert app._search_mode
            assert box.has_focus
            assert table.display

            await pilot.press("a", "l", "p", "h", "a")
            await pilot.pause()
            assert box.value == "alpha"
            assert table.row_count == 1
            assert archive.row_count == 1
            assert archive.display
            assert "1 inbox match and 1 archive match" in str(
                app.query_one("#status", Static).content
            )
            divider = app.query_one("#search_archive_label", Static)
            assert "ARCHIVE · 1 MATCH" in str(divider.content)
            assert divider.region.y == table.region.bottom
            assert archive.region.height > 8

            await pilot.press("escape")
            await pilot.pause()
            assert not app._search_mode
            assert table.row_count == 2
            assert not archive.display

    asyncio.run(run())


def test_search_gives_inbox_rows_the_space_before_showing_archive():
    for i in range(30):
        _add(f"claude:active-{i}", f"common session {i}", 20 + i)
    _add("claude:archive", "common rare archive", 10, "archived")

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 20)) as pilot:
            await pilot.press("/", "c", "o", "m", "m", "o", "n")
            await pilot.pause()
            inbox = app.query_one("#main_table", DataTable)
            archive = app.query_one("#history_table", DataTable)
            divider = app.query_one("#search_archive_label", Static)
            assert inbox.row_count == 30
            assert inbox.region.height > 8
            assert not archive.display
            assert not divider.display
            assert "30 inbox matches and 1 archive match" in str(
                app.query_one("#status", Static).content
            )

            app.query_one("#history_filter", Input).value = "rare"
            await pilot.pause()
            assert inbox.row_count == 0
            assert archive.row_count == 1
            assert archive.display
            assert divider.display
            assert divider.region.y == inbox.region.bottom

    asyncio.run(run())


def test_search_mode_finds_displayed_wordybin_name():
    active = _add("claude:hq", "lemonaid HQ", 20)
    with db.connect() as conn:
        path = brief_store.briefs_dir() / "search-hq.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# hq\n\nBrief-ID: plan-manager.BlessBar\n\nStatus: working\n")
        attached.attach(conn, active.channel, path)
        identity.ensure(conn, path)

    async def run():
        app = LemonaidApp()
        app.config.tui.brief_names_in_inbox = True
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.press("/", "b", "l", "e", "s", "s", "b", "a", "r")
            await pilot.pause()
            table = app.query_one("#main_table", DataTable)
            assert table.row_count == 1
            assert "BlessBar" in " ".join(str(cell) for cell in table.get_row(str(active.id)))

    asyncio.run(run())


def test_search_selects_live_and_archived_rows_differently(monkeypatch):
    _add("claude:active", "match active", 20)
    _add("claude:archive", "match archive", 10, "archived")
    chosen: list[str] = []
    monkeypatch.setattr(
        LemonaidApp,
        "_switch_to_notification",
        lambda self, notification: chosen.append(f"switch:{notification.channel}"),
    )
    monkeypatch.setattr(LemonaidApp, "_resume_session", lambda self: chosen.append("resume"))

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.press("/", "m", "a", "t", "c", "h", "enter")
            await pilot.pause()
            table = app.query_one("#main_table", DataTable)
            archive = app.query_one("#history_table", DataTable)
            assert table.row_count == archive.row_count == 1
            assert table.has_focus
            await pilot.press("enter")
            await pilot.press("down")
            assert archive.has_focus, (app.focused, archive.display, app._search_mode)
            await pilot.press("enter")

    asyncio.run(run())
    assert chosen == ["switch:claude:active", "resume"]


def test_search_filters_the_other_source_section_too(monkeypatch):
    monkeypatch.setattr("lemonaid.inbox.tui.app.detect_terminal_switch_source", lambda: "tmux")
    _add("claude:active", "alpha", 20)
    _add("claude:other-source", "beta", 30, "read", "wezterm")

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause()
            other = app.query_one("#other_sources_table", DataTable)
            assert other.row_count == 1

            await pilot.press("/", "a", "l", "p", "h", "a")
            await pilot.pause()
            assert app.query_one("#main_table", DataTable).row_count == 1
            assert not other.display

    asyncio.run(run())


def test_archive_only_search_focuses_archive():
    _add("claude:active", "current", 20)
    _add("claude:archived", "archive match", 10, "archived")

    async def run():
        app = LemonaidApp()
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.press("/", "m", "a", "t", "c", "h", "enter")
            await pilot.pause()
            main = app.query_one("#main_table", DataTable)
            archive = app.query_one("#history_table", DataTable)
            assert main.row_count == 0
            assert archive.row_count == 1
            assert archive.has_focus

            await pilot.press("escape")
            await pilot.pause()
            assert main.has_focus
            assert not archive.display

    asyncio.run(run())


def test_search_keeps_the_inbox_card_and_blocked_status_fill():
    blocked = _add("claude:blocked", "blocked lemon", 20, "read")
    _add("claude:plain", "other lemon", 30)
    with db.connect() as conn:
        path = brief_store.briefs_dir() / "search-blocked.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# blocked lemon\n\nStatus: blocked\n\n## Now\n")
        attached.attach(conn, blocked.channel, path)

    async def run():
        app = LemonaidApp()
        app.config.tui.brief_status = True
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            table = app.query_one("#main_table", DataTable)
            before = table.get_row(str(blocked.id))[0]
            assert table.row_count == 2

            await pilot.press("/", "b", "l", "o", "c", "k", "e", "d")
            await pilot.pause()
            during = table.get_row(str(blocked.id))[0]
            assert table.row_count == 1
            assert before.plain == during.plain
            assert before.spans == during.spans
            style = during.get_style_at_offset(Console(), during.plain.index("blocked lemon"))
            assert style.bgcolor.name == ATTENTION_COLOR

    asyncio.run(run())


def test_search_keeps_the_wide_inbox_row_fill():
    blocked = _add("claude:blocked", "blocked lemon", 20, "read")
    _add("claude:plain", "other lemon", 30)
    with db.connect() as conn:
        path = brief_store.briefs_dir() / "search-blocked-wide.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# blocked lemon\n\nStatus: blocked\n\n## Now\n")
        attached.attach(conn, blocked.channel, path)

    async def run():
        app = LemonaidApp()
        app.config.tui.brief_status = True
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause()
            table = app.query_one("#main_table", DataTable)
            before = table.get_row(str(blocked.id))
            fill = table.row_backgrounds[str(blocked.id)]
            assert fill.bgcolor is not None

            await pilot.press("/", "b", "l", "o", "c", "k", "e", "d")
            await pilot.pause()
            assert table.row_count == 1
            assert table.get_row(str(blocked.id)) == before
            assert table.row_backgrounds[str(blocked.id)] == fill

    asyncio.run(run())
