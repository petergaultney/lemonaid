"""The scratch sidebar keeps a brief visible and focused beside its lemon."""

import argparse
import asyncio
from pathlib import Path

from textual.widgets import ContentSwitcher, DataTable

from lemonaid.brief import cli, sidebar, target
from lemonaid.inbox import db
from lemonaid.inbox.tui.app import LemonaidApp
from lemonaid.inbox.tui.brief_view import BriefView
from lemonaid.tmux import follow


def _target(tmp_path: Path) -> target.Target:
    path = tmp_path / "task.md"
    path.write_text("# Work\n\nStatus: working\n\n## Now\n- Answer Peter.\n")
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
