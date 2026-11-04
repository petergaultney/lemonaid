"""The scratch sidebar keeps a brief visible and focused beside its lemon."""

import argparse
import asyncio
from pathlib import Path

from textual.widgets import ContentSwitcher, DataTable

from lemonaid import config
from lemonaid.brief import cli, session, sidebar, target
from lemonaid.inbox import db, view
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.briefs.attention_bar import AttentionBar
from lemonaid.inbox.tui.briefs.brief_pane import BriefPane
from lemonaid.inbox.tui.briefs.brief_view import BriefView
from lemonaid.inbox.tui.live import group_headers
from lemonaid.inbox.tui.rows import brief_cards
from lemonaid.inbox.tui.views.usage_screen import UsageScreen
from lemonaid.tmux import follow


def _target(tmp_path: Path) -> target.Target:
    path = tmp_path / "task.md"
    path.write_text("# Work\n\nStatus: working\n\n## Now\n- Answer Sam.\n")
    return target.Target([path], [tmp_path], tmp_path, ["work"], "Work", "**Work**")


def test_sidebar_payload_round_trips(tmp_path):
    found = _target(tmp_path)

    assert sidebar.decode(sidebar._encode(found, "@12")) == (found, "@12")
    assert sidebar.decode("not json") is None


def test_sidebar_falls_back_when_scratch_is_not_beside_target(monkeypatch, tmp_path):
    monkeypatch.setattr(sidebar.scratch, "is_follow_enabled", lambda: True)
    monkeypatch.setattr(sidebar.scratch, "marked_pane", lambda: "%2")
    monkeypatch.setattr(sidebar.scratch, "current_position", lambda _: "left")
    monkeypatch.setattr(sidebar, "window_id", lambda _: "@other")

    assert not sidebar.toggle(_target(tmp_path), "@target")


def test_sidebar_toggle_wakes_scratch_and_closes_on_second_press(monkeypatch, tmp_path):
    options: dict[str, str] = {}
    calls: list[tuple[str, ...]] = []

    def tmux(*args: str) -> str:
        calls.append(args)
        if args[0] == "show-option":
            return options.get(follow.BRIEF_OPTION, "")
        if args[0] == "set-option":
            if "-pu" in args:
                options.pop(follow.BRIEF_OPTION, None)
            else:
                options[follow.BRIEF_OPTION] = args[-1]
        return ""

    monkeypatch.setattr(sidebar, "_tmux", tmux)
    monkeypatch.setattr(sidebar.scratch, "is_follow_enabled", lambda: True)
    monkeypatch.setattr(sidebar.scratch, "marked_pane", lambda: "%2")
    monkeypatch.setattr(sidebar.scratch, "current_position", lambda _: "left")
    monkeypatch.setattr(sidebar, "window_id", lambda _: "@target")
    found = _target(tmp_path)

    assert sidebar.toggle(found, "@target")
    assert sidebar.read("%2") == (found, "@target")
    assert ("switch-client", "-t", "%2") in calls
    assert sidebar.toggle(found, "@target")
    assert sidebar.read("%2") is None
    assert calls.count(("send-keys", "-t", "%2", follow.BRIEF_WAKE_KEY)) == 2
    assert calls.count(("switch-client", "-t", "%2")) == 1


def test_sidebar_show_replaces_brief_in_same_window(monkeypatch, tmp_path):
    options: dict[str, str] = {}
    calls: list[tuple[str, ...]] = []

    def tmux(*args: str) -> str:
        calls.append(args)
        if args[0] == "show-option":
            return options.get(follow.BRIEF_OPTION, "")
        if args[0] == "set-option":
            options[follow.BRIEF_OPTION] = args[-1]
        return ""

    monkeypatch.setattr(sidebar, "_tmux", tmux)
    monkeypatch.setattr(sidebar.scratch, "is_follow_enabled", lambda: True)
    monkeypatch.setattr(sidebar.scratch, "marked_pane", lambda: "%2")
    monkeypatch.setattr(sidebar.scratch, "current_position", lambda _: "left")
    monkeypatch.setattr(sidebar, "window_id", lambda _: "@target")
    first = _target(tmp_path)
    second = target.Target([], [], None, [], "second")

    assert sidebar.show(first, "@target")
    assert sidebar.read("%2") == (first, "@target")
    assert sidebar.show(second, "@target")
    assert sidebar.read("%2") == (second, "@target")
    assert calls.count(("switch-client", "-t", "%2")) == 2


def test_sidebar_falls_back_if_it_cannot_focus_scratch(monkeypatch, tmp_path):
    options: dict[str, str] = {}

    def tmux(*args: str) -> str | None:
        if args[0] == "switch-client":
            return None
        if args[0] == "set-option":
            if "-pu" in args:
                options.pop(follow.BRIEF_OPTION, None)
            else:
                options[follow.BRIEF_OPTION] = args[-1]
        return ""

    monkeypatch.setattr(sidebar, "_tmux", tmux)
    monkeypatch.setattr(sidebar.scratch, "is_follow_enabled", lambda: True)
    monkeypatch.setattr(sidebar.scratch, "marked_pane", lambda: "%2")
    monkeypatch.setattr(sidebar.scratch, "current_position", lambda _: "left")
    monkeypatch.setattr(sidebar, "window_id", lambda _: "@target")

    assert not sidebar.show(_target(tmp_path), "@target")
    assert follow.BRIEF_OPTION not in options


def test_popup_command_prefers_the_sidebar_when_available(monkeypatch, tmp_path):
    found = _target(tmp_path)
    opened: list[target.Target] = []
    monkeypatch.setattr(cli, "_target", lambda *args: found)
    monkeypatch.setattr(sidebar, "window_id", lambda _: "@target")
    monkeypatch.setattr(sidebar, "toggle", lambda item, window: window == "@target")
    monkeypatch.setattr(cli.popup, "open_popup", opened.append)
    args = argparse.Namespace(
        session="work:2",
        file=[],
        dir=[],
        place="",
        name=[],
        target="",
        popup=True,
        page=False,
        dismiss=[],
        use_self=False,
    )

    cli.cmd_show(args)

    assert opened == []


def test_brief_view_replaces_the_inbox_then_restores_it(tmp_path):
    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            table = app.query_one("#main_table", DataTable)
            view = app.query_one(BriefView)
            switcher = app.query_one(ContentSwitcher)
            assert switcher.current == "inbox_content"

            app._set_brief_view(_target(tmp_path))
            await pilot.pause()
            assert switcher.current == "brief_view"
            assert app.sub_title == "brief"
            app._refresh_notifications()
            app._show_keys(False)
            assert switcher.current == "brief_view"

            (tmp_path / "task.md").write_text("# Work\n\nStatus: blocked\n\n## Now\n- Changed.\n")
            app._refresh_notifications()
            await pilot.pause()
            assert "Changed." in view._rendered_markdown
            assert "blocked" in view._rendered_markdown
            assert len(view.query("_Card")) == 1

            app._set_brief_view(None)
            await pilot.pause()
            assert switcher.current == "inbox_content"
            assert table.display
            assert app.sub_title == "attention inbox"

    asyncio.run(check())


def test_b_in_the_sidebar_keeps_focus_on_the_inbox(monkeypatch, tmp_path):
    found = _target(tmp_path)
    with db.connect() as conn:
        row = db.add(
            conn, "claude:brief-test", "working", "work", {"cwd": str(tmp_path), "tty": "/dev/test"}
        )
        conn.execute("UPDATE notifications SET switch_source = 'tmux' WHERE id = ?", (row.id,))
        conn.commit()

    switched: list[int] = []
    monkeypatch.setenv("TMUX_PANE", "%9")
    monkeypatch.setattr("lemonaid.inbox.tui.app.is_follow_enabled", lambda: True)
    monkeypatch.setattr("lemonaid.inbox.tui.app.current_position", lambda _: "left")
    monkeypatch.setattr(
        "lemonaid.inbox.tui.app.brief.attached.for_rows",
        lambda conn, rows: {"claude:brief-test": found.attached[0]},
    )
    monkeypatch.setattr(target, "for_notification", lambda *args: found)
    monkeypatch.setattr(sidebar, "window_id", lambda _: "@target")
    monkeypatch.setattr(sidebar, "toggle", lambda item, window: True)
    monkeypatch.setattr(sidebar, "read", lambda pane: (found, "@target"))
    monkeypatch.setattr(
        LemonaidApp,
        "_switch_to_notification",
        lambda self, notification: switched.append(notification.id) or True,
    )

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            app.action_brief()
            await pilot.pause()
            assert switched == []
            assert app.query_one(ContentSwitcher).current == "brief_view"
            await pilot.press("escape")
            await pilot.pause()
            assert app.query_one(ContentSwitcher).current == "inbox_content"
            app.action_brief()
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            assert app.query_one(ContentSwitcher).current == "inbox_content"

    asyncio.run(check())


def test_hidden_inbox_keys_cannot_archive_a_row(monkeypatch, tmp_path):
    found = _target(tmp_path)
    with db.connect() as conn:
        row = db.add(
            conn, "claude:brief-test", "working", "work", {"cwd": str(tmp_path), "tty": "/dev/test"}
        )
        conn.execute("UPDATE notifications SET switch_source = 'tmux' WHERE id = ?", (row.id,))
        conn.commit()
        original_status = db.get(conn, row.id).status

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            assert app.query_one("#main_table", DataTable).row_count == 1
            app._set_brief_view(found)
            await pilot.press("a")
            await pilot.pause()
            with db.connect() as conn:
                assert db.get(conn, row.id).status == original_status
            assert app.query_one(ContentSwitcher).current == "brief_view"

    asyncio.run(check())


def test_a_sidebar_brief_follows_the_pane_to_another_window(monkeypatch, tmp_path):
    old = _target(tmp_path)
    landed = target.Target([], [tmp_path], tmp_path, ["other"], "Other", "**Other**")
    remembered: list[tuple[str, target.Target, str]] = []
    asked: list[tuple[str, str]] = []
    monkeypatch.setenv("TMUX_PANE", "%9")
    monkeypatch.setattr(sidebar, "read", lambda pane: (old, "@left"))
    monkeypatch.setattr(sidebar, "window_id", lambda _: "@landed")
    monkeypatch.setattr(sidebar, "remember", lambda *args: remembered.append(args))
    monkeypatch.setattr(session, "current_session", lambda: "work:2")

    def for_session(tmux_session, rows, attached, window, emojis):
        asked.append((tmux_session, window))
        return landed

    monkeypatch.setattr(target, "for_session", for_session)
    with db.connect() as conn:
        db.add(conn, "claude:w2", "working", "w2", {"tmux_session": "work", "tmux_window": "2"})

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            app._set_brief_view(old)
            await pilot.pause()
            app.query_one(BriefPane).sync()
            await pilot.pause()
            assert app.query_one(ContentSwitcher).current == "brief_view"
            assert app.query_one(BriefPane).target == landed
            assert asked == [("work", "2")]
            assert remembered == [("%9", landed, "@landed")]

    asyncio.run(check())


def _two_lemons(tmp_path: Path, session: str = "") -> tuple[db.Notification, db.Notification]:
    """Each in its own tmux session, or both in window 1 of *session*."""
    with db.connect() as conn:
        rows = tuple(
            db.add(
                conn,
                f"claude:{name}",
                "working",
                name,
                {"cwd": str(tmp_path), "tmux_session": session or name, "tmux_window": "1"},
            )
            for name in ("first", "second")
        )
        conn.executemany(
            "UPDATE notifications SET switch_source = 'tmux' WHERE id = ?", [(n.id,) for n in rows]
        )
        conn.commit()
    return rows


def _follow_to(monkeypatch, tmp_path: Path, where: str) -> None:
    monkeypatch.setenv("TMUX_PANE", "%9")
    monkeypatch.setattr(sidebar, "read", lambda pane: (_target(tmp_path), "@left"))
    monkeypatch.setattr(sidebar, "window_id", lambda _: "@landed")
    monkeypatch.setattr(sidebar, "remember", lambda *args: None)
    monkeypatch.setattr(session, "current_session", lambda: where)
    monkeypatch.setattr(session, "session_dir", lambda name: tmp_path)


def _is_unread(notification: db.Notification) -> bool:
    with db.connect() as conn:
        return db.get(conn, notification.id).is_unread


def test_keys_act_on_the_lemon_the_brief_followed_to(monkeypatch, tmp_path):
    first, second = _two_lemons(tmp_path)
    _follow_to(monkeypatch, tmp_path, "second:1")

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            table = app.query_one("#main_table", DataTable)
            row_keys = [
                str(table.coordinate_to_cell_key((r, 0))[0].value) for r in range(table.row_count)
            ]
            table.move_cursor(row=row_keys.index(str(first.id)))
            app._set_brief_view(_target(tmp_path))
            app.query_one(BriefPane).sync()
            await pilot.pause()
            assert not app.query_one(BriefPane).unselected
            await pilot.press("M")
            await pilot.pause()
            assert not _is_unread(second)
            assert _is_unread(first)

    asyncio.run(check())


def test_a_brief_for_no_single_row_ignores_single_lemon_keys(monkeypatch, tmp_path):
    first, second = _two_lemons(tmp_path, session="both")
    _follow_to(monkeypatch, tmp_path, "both:1")
    switched: list[int] = []
    monkeypatch.setattr(
        LemonaidApp,
        "_switch_to_notification",
        lambda self, notification: switched.append(notification.id) or True,
    )

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            app._set_brief_view(_target(tmp_path))
            app.query_one(BriefPane).sync()
            await pilot.pause()
            assert app.query_one(BriefPane).unselected
            await pilot.press("M")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert _is_unread(first) and _is_unread(second)
            assert switched == []
            assert app.query_one(ContentSwitcher).current == "brief_view"

    asyncio.run(check())


def test_the_attention_badges_stay_in_the_pane_when_an_open_brief_is_resized(monkeypatch, tmp_path):
    monkeypatch.setattr(LemonaidApp, "_observe_attention", lambda self, frame: None)
    rightmost = [s.name for s in config.brief_statuses()][-1]  # its slot is at the pane's edge
    badge = group_headers.badge(rightmost, 1).plain.strip()
    with db.connect() as conn:
        row = db.add(conn, "claude:sam", "working", "sam", {"cwd": str(tmp_path)})
    active = view.Active(
        [row], {"claude:sam": brief_cards.CardBrief(rightmost, "", 0.0)}, {}, frozenset()
    )

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(70, 30)) as pilot:
            await pilot.pause()
            app._set_brief_view(_target(tmp_path))
            await pilot.pause()
            bar = app.query_one(AttentionBar)
            bar.observe(active)
            await pilot.resize_terminal(45, 30)
            await pilot.pause()
            shown = str(bar.render())
            assert badge in shown
            assert shown.index(badge) + len(badge) <= bar.size.width

    asyncio.run(check())


def test_the_usage_key_opens_usage_over_the_brief_and_closes_it(tmp_path):
    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(60, 30)) as pilot:
            app._set_brief_view(_target(tmp_path))
            await pilot.pause()
            await pilot.press(app.config.tui.keybindings.usage_view)
            await pilot.pause()
            assert isinstance(app.screen, UsageScreen)
            await pilot.press(app.config.tui.keybindings.usage_view)
            await pilot.pause()
            assert not isinstance(app.screen, UsageScreen)
            assert app.query_one(ContentSwitcher).current == "brief_view"

    asyncio.run(check())


def test_a_window_with_no_lemon_keeps_the_brief_shown(monkeypatch, tmp_path):
    _two_lemons(tmp_path)
    shown = _target(tmp_path)
    remembered: list[tuple[str, target.Target, str]] = []
    _follow_to(monkeypatch, tmp_path, "second:3")
    monkeypatch.setattr(sidebar, "remember", lambda *args: remembered.append(args))

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            app._set_brief_view(shown)
            app.query_one(BriefPane).sync()
            await pilot.pause()
            assert app.query_one(BriefPane).target == shown
            assert remembered == [("%9", shown, "@landed")]

    asyncio.run(check())


def test_a_brief_browsed_to_locally_stays_when_a_window_has_no_lemon(monkeypatch, tmp_path):
    _two_lemons(tmp_path)
    browsed = target.Target([], [tmp_path], tmp_path, ["second"], "Second", "**Second**")
    remembered: list[tuple[str, target.Target, str]] = []
    _follow_to(monkeypatch, tmp_path, "second:3")  # the sidebar option still records first's
    monkeypatch.setattr(sidebar, "remember", lambda *args: remembered.append(args))

    async def check() -> None:
        app = LemonaidApp(scratch_mode=True)
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            pane = app.query_one(BriefPane)
            app._set_brief_view(browsed)
            pane.stay_local("Its terminal is unavailable here.")
            pane.sync()
            await pilot.pause()
            assert pane.target == browsed
            assert remembered == [("%9", browsed, "@landed")]

    asyncio.run(check())
